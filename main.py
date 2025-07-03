import os
import json
import argparse
import asyncio
from telethon.sync import TelegramClient
from telethon.tl.types import Document
from tqdm import tqdm
from config import * 


def get_files(directory):
    part_files = sorted([
        os.path.join(directory, f)
        for f in os.listdir(directory)
        if '.part' in f
    ])
    
    return part_files


def split_file(file_path):
    print(f"[+] Splitting file: {file_path}")
    chunks = []
    with open(file_path, 'rb') as f:
        i = 0
        while True:
            chunk = f.read(CHUNK_SIZE)
            if not chunk:
                break
            chunk_name = f"{file_path}.part{i:03}"
            with open(chunk_name, 'wb') as out:
                out.write(chunk)
            chunks.append(chunk_name)
            i += 1
            print(f"  - Created chunk: {chunk_name}")
    return chunks


def merge_chunks(output_file, chunk_files):
    print(f"[+] Merging to: {output_file}")
    with open(output_file, 'wb') as out:
        for chunk_file in sorted(chunk_files):
            print(f"  - Merging: {chunk_file}")
            with open(chunk_file, 'rb') as chunk:
                out.write(chunk.read())

    print("[✓] Merge complete. Deleting part files...")
    for chunk_file in chunk_files:
        try:
            os.remove(chunk_file)
            print(f"  - Deleted: {chunk_file}")
        except Exception as e:
            print(f"  ! Could not delete {chunk_file}: {e}")

    print("[✓] All part files deleted.")


async def upload_chunks(client, chunk_paths):
    print(f"[+] Uploading {len(chunk_paths)} chunks...")
    metadata = []

    for chunk_path in chunk_paths:
        chunk_size = os.path.getsize(chunk_path)
        progress_bar = tqdm(total=chunk_size, unit='B', unit_scale=True, desc=os.path.basename(chunk_path))

        def progress_callback(current, total):
            progress_bar.n = current
            progress_bar.refresh()

        msg = await client.send_file(
            CHANNEL_USERNAME,
            chunk_path,
            caption=os.path.basename(chunk_path),
            progress_callback=progress_callback
        )
        progress_bar.close()

        metadata.append({
            "message_id": msg.id,
            "filename": os.path.basename(chunk_path)
        })
        print(f"  - Uploaded: {chunk_path}")

    os.makedirs('manifests', exist_ok=True)
    manifest_path = os.path.join('manifests', 'file_manifest.json')
    with open(manifest_path, 'w') as f:
        json.dump(metadata, f, indent=2)

    print(f"[✓] Upload complete. Metadata saved as {manifest_path}")


async def download_chunks(client, manifest_path):
    print(f"[+] Downloading chunks from: {manifest_path}")
    with open(manifest_path, 'r') as f:
        manifest = json.load(f)

    os.makedirs('downloads', exist_ok=True)
    for entry in manifest:
        msg = await client.get_messages(CHANNEL_USERNAME, ids=entry["message_id"])
        out_path = os.path.join('downloads', entry["filename"])
        await client.download_media(msg, file=out_path)
        print(f"  - Downloaded: {entry['filename']}")
    print("[✓] Download complete.")


def main():
    parser = argparse.ArgumentParser(description="Telegram File Splitter & Storage")
    subparsers = parser.add_subparsers(dest="command")

    sp_split = subparsers.add_parser("split", help="Split large file")
    sp_split.add_argument("filepath", help="Path to file to split")

    sp_upload = subparsers.add_parser("upload", help="Upload split chunks to Telegram")
    sp_upload.add_argument("chunk_dir", help="Directory with .partXXX files")

    sp_download = subparsers.add_parser("download", help="Download chunks using manifest")
    sp_download.add_argument("manifest", help="Path to file_manifest.json")

    sp_merge = subparsers.add_parser("merge", help="Merge downloaded chunks")
    sp_merge.add_argument("output", help="Output file name")
    sp_merge.add_argument("parts_dir", help="Directory with downloaded .part files")

    args = parser.parse_args()

    if args.command == "split":
        split_file(args.filepath)

    elif args.command == "merge":
        merge_chunks(args.output, get_files(args.parts_dir))

    elif args.command == "upload":
        async def upload_main():
            async with TelegramClient(SESSION_NAME, API_ID, API_HASH) as client:
                await upload_chunks(client, get_files(args.chunk_dir))
        asyncio.run(upload_main())

    elif args.command == "download":
        async def download_main():
            async with TelegramClient(SESSION_NAME, API_ID, API_HASH) as client:
                await download_chunks(client, args.manifest)
        asyncio.run(download_main())
    
    else:
        parser.print_help()


if __name__ == "__main__":
    main()