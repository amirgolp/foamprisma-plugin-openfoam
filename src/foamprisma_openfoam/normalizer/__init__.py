"""
OpenFOAMNormalizer — runs after the parser has populated `OpenFOAMCase`.

Three concerns, in priority order:
  1. Defensive case_type inference from solver_name when the parser couldn't
     determine it.
  2. Field validation — warn (don't fail) on missing required fields so users
     see a clear log entry rather than a silent half-populated entry.
  3. Best-effort Reynolds number from transportProperties (kinematic viscosity)
     and a representative inlet velocity. If neither is derivable from the
     archive alone, skip silently — v1 does not re-read raw files here.
"""

from __future__ import annotations

try:
    from nomad.config.models.plugins import (
        NormalizerEntryPoint as _NormalizerEntryPoint,
    )
except ImportError:
    from pydantic import BaseModel as _NormalizerEntryPoint  # type: ignore[assignment]


# ── solver_name → case_type lookup table ───────────────────────────────────
# Conservative: only well-known mappings. Anything not listed stays as-is
# (or 'other' if case_type is missing).
_SOLVER_CATEGORY: dict[str, str] = {
    # Incompressible
    "icoFoam": "incompressible",
    "simpleFoam": "incompressible",
    "pimpleFoam": "incompressible",
    "pisoFoam": "incompressible",
    "potentialFoam": "incompressible",
    "porousSimpleFoam": "incompressible",
    "shallowWaterFoam": "incompressible",
    # Compressible
    "rhoSimpleFoam": "compressible",
    "rhoPimpleFoam": "compressible",
    "rhoCentralFoam": "compressible",
    "sonicFoam": "compressible",
    "rhoPorousMRFPimpleFoam": "compressible",
    # Multiphase
    "interFoam": "multiphase",
    "multiphaseInterFoam": "multiphase",
    "twoPhaseEulerFoam": "multiphase",
    "compressibleInterFoam": "multiphase",
    "cavitatingFoam": "multiphase",
    # Combustion
    "reactingFoam": "combustion",
    "fireFoam": "combustion",
    "XiFoam": "combustion",
    "chemFoam": "combustion",
    # Heat transfer / buoyancy
    "chtMultiRegionFoam": "heat-transfer",
    "buoyantSimpleFoam": "heat-transfer",
    "buoyantPimpleFoam": "heat-transfer",
    "buoyantBoussinesqSimpleFoam": "heat-transfer",
    # Electromagnetics
    "magneticFoam": "electromagnetics",
    "mhdFoam": "electromagnetics",
    # Stress / FSI
    "solidDisplacementFoam": "stress-analysis",
}


def _infer_case_type(solver_name: str | None) -> str | None:
    if not solver_name:
        return None
    return _SOLVER_CATEGORY.get(solver_name)


def _required_field_warnings(case) -> list[str]:
    """Return a list of human-readable warnings for missing required fields."""
    warnings: list[str] = []
    if not case.case_name:
        warnings.append("case_name is empty")
    if not case.solver_name:
        warnings.append("solver_name is empty")
    if case.mesh is None:
        warnings.append("mesh subsection missing entirely")
    elif case.mesh.n_cells in (None, 0):
        warnings.append("mesh.n_cells not populated")
    return warnings


def _compute_reynolds(case) -> float | None:
    """
    Best-effort Reynolds number from data already in the archive. Two channels:

    1. solver_config.relaxation_factors / .solvers may carry parsed values from
       transportProperties (some PyFoam adapters fold them in). We don't rely on this.
    2. If the schema later grows explicit `kinematic_viscosity` and `inlet_velocity`
       fields on solver_config, this function will start producing values.

    Until the parser+schema expose those values, this returns None — leaving the
    quantity unset. The normalizer logs that Reynolds was not derivable.
    """
    sc = getattr(case, "solver_config", None)
    if sc is None:
        return None

    nu = getattr(sc, "kinematic_viscosity", None)
    u_ref = getattr(sc, "reference_velocity", None)
    l_ref = getattr(sc, "characteristic_length", None)

    if nu in (None, 0) or u_ref in (None, 0) or l_ref in (None, 0):
        return None

    return float(u_ref) * float(l_ref) / float(nu)


def _normalize_case(case, logger) -> None:
    """Pure-function normalizer body.

    Defined at module level (no nomad imports) so it's importable from tests
    and from the lazy class built inside OpenFOAMNormalizerEntryPoint.load().
    """
    # 1. Defensive case_type
    if not case.case_type:
        inferred = _infer_case_type(case.solver_name)
        if inferred:
            case.case_type = inferred
            if logger:
                logger.info(
                    "OpenFOAMNormalizer: inferred case_type",
                    solver_name=case.solver_name,
                    case_type=inferred,
                )
        elif case.solver_name:
            case.case_type = "other"
            if logger:
                logger.warn(
                    "OpenFOAMNormalizer: solver_name not in lookup table",
                    solver_name=case.solver_name,
                )

    # 2. Required-field validation
    for warning in _required_field_warnings(case):
        if logger:
            logger.warn(f"OpenFOAMNormalizer: {warning}", entry=case.case_name or "?")

    # 3. Best-effort Reynolds
    if case.reynolds_number in (None, 0):
        re = _compute_reynolds(case)
        if re is not None:
            case.reynolds_number = re
            if logger:
                logger.info("OpenFOAMNormalizer: computed Reynolds number", re=re)
        elif logger:
            logger.info(
                "OpenFOAMNormalizer: Reynolds not derivable from current archive "
                "(kinematic_viscosity / reference_velocity / characteristic_length absent)"
            )


class OpenFOAMNormalizerEntryPoint(_NormalizerEntryPoint):
    """Entry point so NOMAD discovers and registers the normalizer.

    The actual Normalizer subclass is built inside load() so that
    `from nomad.normalizing.normalizer import Normalizer` only fires when
    the entry point is loaded by NOMAD's plugin system — long after
    nomad.datamodel finishes initialising. Importing it at module top
    triggers a circular import: nomad.datamodel.metainfo.__init__ calls
    config.load_plugins(), which imports us, which imports
    nomad.normalizing, which imports nomad.datamodel — still partially
    initialised.
    """

    def load(self):  # type: ignore[override]
        from nomad.normalizing.normalizer import Normalizer

        class OpenFOAMNormalizer(Normalizer):
            def normalize(self, archive, logger=None) -> None:
                from foamprisma_openfoam.schema.case import OpenFOAMCase

                case = getattr(archive, "data", None)
                if not isinstance(case, OpenFOAMCase):
                    return
                _normalize_case(case, logger)

        return OpenFOAMNormalizer()


openfoam_normalizer_entry_point = OpenFOAMNormalizerEntryPoint(
    name="OpenFOAMNormalizer",
    description=(
        "Defensively infers case_type from solver_name, validates required "
        "fields, and computes Reynolds number when derivable."
    ),
    level=10,
)
