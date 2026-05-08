try:
    from nomad.config.models.plugins import SchemaPackageEntryPoint as _Base
except ImportError:
    from pydantic import BaseModel as _Base  # type: ignore[assignment]


class OpenFOAMSchemaEntryPoint(_Base):
    def load(self):
        from foamprisma_openfoam.schema.case import m_package

        return m_package


openfoam_schema_entry_point = OpenFOAMSchemaEntryPoint(
    name="OpenFOAMSchema",
    description="Schema package for OpenFOAM simulation data.",
)
