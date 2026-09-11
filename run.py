if __name__ == "__main__":
    import sys
    try:
        from localdrop.app import main
        raise SystemExit(main())
    except Exception:
        # Opt-in diagnostics must report startup errors without a modal dialog.
        if len(sys.argv) == 3 and sys.argv[1] == "--self-test":
            import json
            from pathlib import Path
            import traceback
            output = Path(sys.argv[2]).resolve()
            output.mkdir(parents=True, exist_ok=True)
            (output / "result.json").write_text(json.dumps({"passed": False, "error": traceback.format_exc()}, indent=2))
            raise SystemExit(1)
        raise
