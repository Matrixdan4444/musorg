class Context:
    def __init__(
        self,
        root_path,
        dry_run: bool = False,
        output_root: str | None = None,
        developer_mode: bool = False,
        run_id: str | None = None,
        log_broadcaster=None,
        staged_album_overrides: dict | None = None,
        output_format_settings: dict | None = None,
        metadata_preservation_settings: dict | None = None,
        duplicate_handling: str = "keep_everything",
        filename_compatibility: str = "preserve_original",
    ):
        self.root_path = root_path
        self.dry_run = dry_run
        self.output_root = output_root
        self.developer_mode = developer_mode
        self.run_id = run_id
        self.log_broadcaster = log_broadcaster
        self.staged_album_overrides = staged_album_overrides or {}
        self.output_format_settings = output_format_settings or {}
        self.metadata_preservation_settings = metadata_preservation_settings or {}
        self.duplicate_handling = duplicate_handling
        self.filename_compatibility = filename_compatibility

        self.files = []
        self.cue_albums = []
        self.tracks = []
        self.albums = {}
        self.resolved_album_metadata = {}
        self.metadata_intelligence_by_album_id = {}

        self.errors = []
        self.operation_journal = None
        self.run_report = None
