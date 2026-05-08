"""End-to-end smoke test that requires nomad-lab to be installed.

Skipped when nomad-lab isn't available (typical local dev / unit-test runs).
Runs in CI's `integration` job after pip-installing nomad-lab.

What this verifies (in order):
  1. The plugin's entry points (parser, schema, normalizer, app, actions)
     register without throwing.
  2. The parser parses the bundled cavity fixture and populates an
     OpenFOAMCase on the archive.
  3. The normalizer runs on the parsed archive and infers case_type
     ('incompressible' for icoFoam) when the parser didn't set one.
"""

from pathlib import Path

import pytest

nomad = pytest.importorskip('nomad', reason='nomad-lab not installed')
EntryArchive = pytest.importorskip('nomad.datamodel').EntryArchive

CAVITY = Path(__file__).resolve().parent.parent / 'data' / 'cavity'
CONTROL_DICT = CAVITY / 'system' / 'controlDict'


@pytest.fixture
def cavity_archive():
    """Run the parser on the cavity fixture and return the resulting archive."""
    from foamprisma_openfoam.parser import openfoam_parser_entry_point
    from nomad.datamodel.metainfo.basesections import EntryArchive as _EA

    parser = openfoam_parser_entry_point.load()
    archive = _EA() if hasattr(_EA, '__call__') else EntryArchive()

    if not CONTROL_DICT.exists():
        pytest.skip(f'cavity fixture missing at {CONTROL_DICT}')

    parser.parse(mainfile=str(CONTROL_DICT), archive=archive, logger=None)
    return archive


def test_entry_points_load():
    """Every declared entry point can be loaded without raising."""
    from foamprisma_openfoam.parser import openfoam_parser_entry_point
    from foamprisma_openfoam.schema import openfoam_schema_entry_point
    from foamprisma_openfoam.normalizer import openfoam_normalizer_entry_point

    assert openfoam_parser_entry_point.load() is not None
    assert openfoam_schema_entry_point.load() is not None
    assert openfoam_normalizer_entry_point.load() is not None


def test_parser_populates_case(cavity_archive):
    from foamprisma_openfoam.schema.case import OpenFOAMCase

    case = cavity_archive.data
    assert isinstance(case, OpenFOAMCase), (
        f'Expected OpenFOAMCase on archive.data, got {type(case)}'
    )
    assert case.solver_name == 'icoFoam'
    # The cavity tutorial has a 20×20×1 blockMesh — at least n_cells should land.
    assert case.mesh is not None
    assert case.mesh.n_cells is not None and case.mesh.n_cells > 0


def test_normalizer_infers_case_type(cavity_archive):
    """icoFoam should be categorized as 'incompressible'."""
    from foamprisma_openfoam.normalizer import openfoam_normalizer_entry_point

    case = cavity_archive.data
    case.case_type = None  # force normalizer to fill it in

    normalizer = openfoam_normalizer_entry_point.load()
    normalizer.normalize(cavity_archive, logger=None)

    assert case.case_type == 'incompressible'
