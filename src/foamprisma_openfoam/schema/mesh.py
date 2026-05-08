from nomad.metainfo import MSection, Quantity, MEnum


class OpenFOAMMesh(MSection):
    """Mesh information for an OpenFOAM case."""

    mesh_type = Quantity(
        type=MEnum("blockMesh", "snappyHexMesh", "cfMesh", "imported", "unknown"),
        description="Mesh generation method.",
    )
    n_cells = Quantity(type=int, description="Total number of cells.")
    n_faces = Quantity(type=int, description="Total number of faces.")
    n_points = Quantity(type=int, description="Total number of points.")
    n_internal_faces = Quantity(type=int, description="Number of internal faces.")
    n_boundary_patches = Quantity(type=int, description="Number of boundary patches.")
