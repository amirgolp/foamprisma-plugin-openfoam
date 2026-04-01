from nomad.config.models.plugins import NORTHTool, NorthToolEntryPoint

openfoam_north_tool = NORTHTool(
    image='ghcr.io/amirgolp/foamprisma-core/openfoam-north:main',
    description=(
        '### OpenFOAM v2212\n\n'
        'JupyterLab environment with OpenFOAM v2212 pre-installed. '
        'Run solvers, blockMesh, snappyHexMesh, and post-processing utilities '
        'directly in the terminal. The FoamPrisma plugin is available for '
        'programmatic access to case data via Python.'
    ),
    short_description='OpenFOAM v2212 + JupyterLab',
    file_extensions=['foam'],
    image_pull_policy='Always',
    default_url='/lab',
    maintainer=[{'email': 'me@my-oasis.org', 'name': 'FoamPrisma'}],
    mount_path='/home/jovyan',
    path_prefix='lab/tree',
    privileged=False,
    with_path=True,
    display_name='OpenFOAM',
)

openfoam_north = NorthToolEntryPoint(
    id_url_safe='openfoam-north',
    north_tool=openfoam_north_tool,
)
