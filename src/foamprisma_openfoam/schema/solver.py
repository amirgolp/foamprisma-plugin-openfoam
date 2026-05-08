"""
Solver configuration schema with ELN annotations for interactive viewing/editing.
Corresponds to system/controlDict, system/fvSchemes, system/fvSolution.
"""

from nomad.metainfo import MSection, Quantity, Section, JSON
from nomad.datamodel.metainfo.annotations import ELNAnnotation, ELNComponentEnum
import numpy as np


class SolverConfiguration(MSection):
    """
    Solver settings parsed from controlDict, fvSchemes, fvSolution.
    Rendered in the GUI as an organized form with editable fields.
    """

    m_def = Section(
        a_eln=ELNAnnotation(lane_width="800px"),
    )

    # ── controlDict ──
    application = Quantity(
        type=str,
        description="Solver application name from controlDict",
        a_eln=ELNAnnotation(component=ELNComponentEnum.StringEditQuantity),
    )
    start_time = Quantity(
        type=np.float64,
        unit="second",
        description="Simulation start time",
        a_eln=ELNAnnotation(component=ELNComponentEnum.NumberEditQuantity),
    )
    end_time = Quantity(
        type=np.float64,
        unit="second",
        description="Simulation end time",
        a_eln=ELNAnnotation(component=ELNComponentEnum.NumberEditQuantity),
    )
    delta_t = Quantity(
        type=np.float64,
        unit="second",
        description="Time step (deltaT)",
        a_eln=ELNAnnotation(component=ELNComponentEnum.NumberEditQuantity),
    )
    write_interval = Quantity(
        type=np.float64,
        description="Write interval for output",
        a_eln=ELNAnnotation(component=ELNComponentEnum.NumberEditQuantity),
    )
    write_format = Quantity(
        type=str,
        description="Write format (ascii/binary)",
    )
    write_compression = Quantity(
        type=str,
        description="Write compression (compressed/uncompressed)",
    )

    # ── fvSchemes ──
    time_scheme = Quantity(
        type=str,
        description="ddtSchemes default (e.g., Euler, backward, CrankNicolson)",
        a_eln=ELNAnnotation(component=ELNComponentEnum.StringEditQuantity),
    )
    grad_schemes = Quantity(
        type=JSON,
        description="Gradient discretization schemes from fvSchemes",
    )
    div_schemes = Quantity(
        type=JSON,
        description="Divergence discretization schemes from fvSchemes",
    )
    laplacian_schemes = Quantity(
        type=JSON,
        description="Laplacian discretization schemes from fvSchemes",
    )
    interpolation_schemes = Quantity(
        type=JSON,
        description="Interpolation schemes from fvSchemes",
    )

    # ── fvSolution ──
    solvers = Quantity(
        type=JSON,
        description="Linear solver settings per field from fvSolution",
    )
    relaxation_factors = Quantity(
        type=JSON,
        description="Under-relaxation factors from fvSolution",
    )
    n_correctors = Quantity(
        type=int,
        description="Number of PISO/PIMPLE correctors",
        a_eln=ELNAnnotation(component=ELNComponentEnum.NumberEditQuantity),
    )
    n_non_orthogonal_correctors = Quantity(
        type=int,
        description="Number of non-orthogonal correctors",
        a_eln=ELNAnnotation(component=ELNComponentEnum.NumberEditQuantity),
    )

    # ── Turbulence ──
    turbulence_model = Quantity(
        type=str,
        description="Turbulence model (e.g., kOmegaSST, kEpsilon, laminar)",
        a_eln=ELNAnnotation(component=ELNComponentEnum.StringEditQuantity),
    )
    turbulence_type = Quantity(
        type=str,
        description="RAS, LES, or laminar",
    )

    # ── Parallel ──
    n_subdomains = Quantity(
        type=int,
        description="Number of subdomains from decomposeParDict",
    )
    decomposition_method = Quantity(
        type=str,
        description="Decomposition method (scotch, hierarchical, simple)",
    )
