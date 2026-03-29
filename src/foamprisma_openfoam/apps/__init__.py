"""
FoamPrisma custom search apps.

Defines the 'OpenFOAM Simulations' app that appears in the NOMAD GUI sidebar.
This replaces the material-science-specific apps with an OpenFOAM-focused browser.
"""

from nomad.config.models.plugins import AppEntryPoint
from nomad.config.models.ui import (
    App, Axis, AxisScale, Column, Columns, Dashboard, FilterMenu, FilterMenus,
    Filters, Layout, WidgetHistogram, WidgetTerms,
)

_SCHEMA = 'foamprisma_openfoam.schema.case.OpenFOAMCase'
def _Q(field):
    return f'data.{field}#{_SCHEMA}'


def _LG_LAYOUT(w, h, x, y):
    return {'lg': Layout(w=w, h=h, x=x, y=y, minH=3, minW=3)}


openfoam_app = AppEntryPoint(
    name='OpenFOAM Simulations',
    description='Browse and search OpenFOAM simulation data.',
    app=App(
        label='OpenFOAM Simulations',
        path='simulations',
        category='Use Cases',
        description='Search and browse uploaded OpenFOAM cases.',
        readme='Upload OpenFOAM case directories to index them. Each case with a `system/controlDict` is automatically parsed.',

        # ── Search filters in the sidebar ──
        filters=Filters(
            include=[f'*#{_SCHEMA}'],
        ),
        filters_locked={
            'section_defs.definition_qualified_name': [_SCHEMA],
        },

        # ── Result table columns ──
        columns=Columns(
            selected=[
                _Q('case_name'),
                _Q('solver_name'),
                _Q('case_type'),
                _Q('mesh.n_cells'),
                _Q('mesh.mesh_type'),
                _Q('results.converged'),
                'upload_create_time',
                'authors',
            ],
            options={
                _Q('case_name'): Column(label='Case Name', align='left'),
                _Q('solver_name'): Column(label='Solver'),
                _Q('case_type'): Column(label='Type'),
                _Q('mesh.n_cells'): Column(label='Cells'),
                _Q('mesh.mesh_type'): Column(label='Mesh Method'),
                _Q('results.converged'): Column(label='Converged'),
                'upload_create_time': Column(label='Uploaded'),
                'authors': Column(label='Author'),
            },
        ),

        # ── Filter menus ──
        filter_menus=FilterMenus(
            options={
                'solver': FilterMenu(label='Solver', level=0),
                'mesh': FilterMenu(label='Mesh', level=0),
                'metadata': FilterMenu(label='Metadata', level=0),
                'author': FilterMenu(label='Author', level=0, size='s'),
            },
        ),

        # ── Dashboard widgets ──
        dashboard=Dashboard(
            widgets=[
                WidgetTerms(
                    search_quantity=_Q('solver_name'),
                    layout=_LG_LAYOUT(6, 8, 0, 0),
                    title='Solver Distribution',
                ),
                WidgetTerms(
                    search_quantity=_Q('case_type'),
                    layout=_LG_LAYOUT(6, 8, 6, 0),
                    title='Case Types',
                ),
                WidgetTerms(
                    search_quantity=_Q('mesh.mesh_type'),
                    layout=_LG_LAYOUT(6, 8, 0, 8),
                    title='Mesh Generation Methods',
                ),
                WidgetHistogram(
                    x=Axis(search_quantity=_Q('mesh.n_cells')),
                    y=AxisScale(),
                    layout=_LG_LAYOUT(6, 8, 6, 8),
                    title='Cell Count Distribution',
                    nbins=20,
                ),
            ],
        ),
    ),
)
