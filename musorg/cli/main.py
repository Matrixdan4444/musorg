import click

from musorg.core.audit import audit_library, format_audit_summary
from musorg.core.match_stress import run_match_stress
from musorg.core.pipeline import run_pipeline


class DefaultToRunGroup(click.Group):
    default_command_name = "run"

    def parse_args(self, ctx, args):
        if args and args[0] not in self.commands and args[0] not in ctx.help_option_names:
            args.insert(0, self.default_command_name)
        return super().parse_args(ctx, args)

@click.group(cls=DefaultToRunGroup)
def run():
    pass


@run.command("run")
@click.argument("path")
@click.option("--dry-run", is_flag=True, help="Preview moves, tags, and downloads without changing files.")
def run_command(path, dry_run):
    run_pipeline(path, apply=not dry_run)


@run.command("audit")
@click.argument("path")
@click.option("--json", "json_output", is_flag=True, help="Print the audit report as JSON.")
@click.option("--verbose", is_flag=True, help="Show detailed file and album findings.")
def audit_command(path, json_output, verbose):
    report = audit_library(path)
    if json_output:
        click.echo(report.to_json())
        return
    click.echo(format_audit_summary(report, verbose=verbose))


@run.command("match-stress")
@click.argument("path")
@click.option("--json-out", type=click.Path(dir_okay=False, path_type=str), help="Write the JSON report to PATH.")
@click.option("--workers", default=2, show_default=True, type=int, help="Maximum concurrent provider lookups.")
@click.option("--limit", type=int, help="Process only the first N grouped lookups.")
@click.option("--use-cache", is_flag=True, help="Allow provider cache reads/writes for this run.")
@click.option("--verbose", is_flag=True, help="Print top provider failure reasons in the console summary.")
def match_stress_command(path, json_out, workers, limit, use_cache, verbose):
    run_match_stress(
        path,
        json_out=json_out,
        workers=workers,
        limit=limit,
        use_cache=use_cache,
        verbose=verbose,
    )


if __name__ == "__main__":
    run()
