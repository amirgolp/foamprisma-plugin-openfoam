try:
    from nomad.config.models.plugins import ParserEntryPoint as _Base
except ImportError:
    from pydantic import BaseModel as _Base  # type: ignore[assignment]


class OpenFOAMParserEntryPoint(_Base):
    def load(self):
        # Thread the mainfile regexes from the entry-point declaration into
        # the MatchingParser base class. Without this OpenFOAMParser falls
        # back to the default `mainfile_name_re=.*` and matches every text
        # file in an upload — every file ends up as an entry assigned to
        # this parser, then fails when parse() tries to derive a case dir.
        from foamprisma_openfoam.parser.openfoam_parser import OpenFOAMParser

        return OpenFOAMParser(
            name=self.name,
            mainfile_name_re=self.mainfile_name_re,
            mainfile_mime_re=self.mainfile_mime_re,
        )


openfoam_parser_entry_point = OpenFOAMParserEntryPoint(
    name="OpenFOAMParser",
    description="Parser for OpenFOAM simulation case directories.",
    mainfile_name_re=r".*/system/controlDict$",
    mainfile_mime_re="text/plain",
)
