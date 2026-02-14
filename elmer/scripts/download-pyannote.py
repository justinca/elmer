"""Download pyannote speaker-diarization-3.1 model for offline use.

Run once on the Windows worker machine:
    set HF_TOKEN=hf_xxxxx
    python scripts/download-pyannote.py

After download, the model is cached locally and no token is needed at runtime.
"""

import os
import sys


def main():
    token = os.environ.get("HF_TOKEN", "")
    if not token:
        print("ERROR: Set HF_TOKEN environment variable first.")
        print()
        print("  1. Accept license at https://huggingface.co/pyannote/speaker-diarization-3.1")
        print("  2. Create token at https://huggingface.co/settings/tokens")
        print("  3. set HF_TOKEN=hf_xxxxx")
        sys.exit(1)

    print("Downloading pyannote/speaker-diarization-3.1...")
    from pyannote.audio import Pipeline

    pipeline = Pipeline.from_pretrained(
        "pyannote/speaker-diarization-3.1",
        token=token,
    )
    print("Download complete!")
    print(f"Model cached at: {os.path.expanduser('~/.cache/huggingface/hub/')}")
    print("The HF_TOKEN is no longer needed for runtime operation.")


if __name__ == "__main__":
    main()
