from nomad.metainfo import MSection, Quantity


class BoundaryConditions(MSection):
    """A single boundary patch with its condition type."""

    patch_name = Quantity(type=str, description="Name of the boundary patch.")
    patch_type = Quantity(
        type=str,
        description="OpenFOAM boundary type (e.g., wall, inlet, outlet, symmetry).",
    )
    velocity_bc = Quantity(
        type=str,
        description="Velocity boundary condition type (e.g., fixedValue, zeroGradient).",
    )
    pressure_bc = Quantity(
        type=str,
        description="Pressure boundary condition type.",
    )
    temperature_bc = Quantity(
        type=str,
        description="Temperature boundary condition type (if applicable).",
    )
