try:
    from nomad.config.models.plugins import ParserEntryPoint as _Base
except ImportError:
    from pydantic import BaseModel as _Base  # type: ignore[assignment]


class OpenFOAMParserEntryPoint(_Base):
    def load(self):
        from foamprisma_openfoam.parser.openfoam_parser import OpenFOAMParser
        return OpenFOAMParser()


openfoam_parser_entry_point = OpenFOAMParserEntryPoint(
    name='OpenFOAMParser',
    description='Parser for OpenFOAM simulation case directories.',
    mainfile_name_re=r'.*/system/controlDict$',
    mainfile_mime_re='text/plain',
)
