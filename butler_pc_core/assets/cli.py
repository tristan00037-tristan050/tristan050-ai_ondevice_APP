from __future__ import annotations

import argparse
from pathlib import Path

from .contracts import ReleaseProfile
from .errors import AssetError
from .generator import stage_assets
from .offline import verify_release_package


def _stage(args: argparse.Namespace) -> None:
    stage_assets(
        source_root=args.source_root,
        inventory_path=args.inventory,
        resources_root=args.resources_root,
        source_commit=args.source_commit,
        source_tree=args.source_tree,
        release_profile=args.release_profile,
    )
    print("ASSET_STAGE_OK=1")


def _verify(args: argparse.Namespace) -> None:
    package = args.package or args.resources_root
    verify_release_package(
        package=package,
        build_context=args.build_context,
        release_profile=args.release_profile,
    )
    print("ASSET_RELEASE_VERIFY_OK=1")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Butler sealed asset tooling")
    sub = parser.add_subparsers(dest="command", required=True)
    stage = sub.add_parser("stage")
    stage.add_argument("--source-root", type=Path, required=True)
    stage.add_argument("--inventory", type=Path, required=True)
    stage.add_argument("--resources-root", type=Path, required=True)
    stage.add_argument("--source-commit", required=True)
    stage.add_argument("--source-tree", required=True)
    stage.add_argument(
        "--release-profile",
        choices=[item.value for item in ReleaseProfile],
        required=True,
    )
    stage.set_defaults(handler=_stage)
    verify = sub.add_parser("verify-release")
    source = verify.add_mutually_exclusive_group(required=True)
    source.add_argument("--package", type=Path)
    source.add_argument("--resources-root", type=Path)
    verify.add_argument("--build-context", type=Path)
    verify.add_argument(
        "--release-profile",
        choices=[item.value for item in ReleaseProfile],
        required=True,
    )
    verify.set_defaults(handler=_verify)
    return parser


def main() -> int:
    args = _parser().parse_args()
    try:
        args.handler(args)
    except AssetError as exc:
        print("ASSET_COMMAND_OK=0")
        print(f"ERROR_CODE={exc.code}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
