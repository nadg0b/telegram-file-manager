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


async def upload_files(client, file_paths):
    print(f"[+] Uploading {len(file_paths)} files...")
    metadata = []

    for path in file_paths:
        file_size = os.path.getsize(path)
        file_name = os.path.basename(path)
        origin = file_name[:file_name.rfind(".part")] if ".part" in file_name else file_name

        progress_bar = tqdm(total=file_size, unit='B', unit_scale=True, desc=file_name)

        def progress_callback(current, total):
            progress_bar.n = current
            progress_bar.refresh()

        msg = await client.send_file(
            CHANNEL_USERNAME,
            path,
            caption=file_name,
            progress_callback=progress_callback
        )
        progress_bar.close()

        print(f"  - Uploaded: {path}")

        metadata.append({
            "message_id": msg.id,
            "filename": file_name,
            "size": file_size,
            "date": msg.date.isoformat(),
            "origin": origin 
        })
        
    if os.path.exists(DEFAULT_MANIFEST):
        with open(DEFAULT_MANIFEST, 'r') as f:
            prev_metadata = json.load(f)
    else:
        prev_metadata = []

    prev_metadata.extend(metadata)

    with open(DEFAULT_MANIFEST, 'w') as f:
        json.dump(prev_metadata, f, indent=2)

    print(f"[✓] Upload complete. Metadata saved as {DEFAULT_MANIFEST}")

    print(f"[+] Cleaning up '{DEFAULT_FILES_DIR}' folder...")
    for filename in os.listdir(DEFAULT_FILES_DIR):
        file_path = os.path.join(DEFAULT_FILES_DIR, filename)
        if os.path.isfile(file_path):
            try:
                os.remove(file_path)
                print(f"  - Deleted: {file_path}")
            except Exception as e:
                print(f"  ! Could not delete {file_path}: {e}")
    print("[✓] All files deleted.")


async def download_files(client):
    print(f"[+] Downloading from: {DEFAULT_MANIFEST}")
    with open(DEFAULT_MANIFEST, 'r') as f:
        manifest = json.load(f)

    file_list = {}

    for entry in manifest:
        if entry["origin"] not in file_list:
            files = list(filter(lambda x: x["origin"] == entry["origin"], manifest))

            file_list[entry["origin"]] = {
                                            "parts": files, 
                                            "size": sum(x["size"] for x in files),
                                            "date": entry["date"]
                                        }

    print("[+] Available files:")
    for i, (origin, info) in enumerate(file_list.items()):  
        print(f"{i:3}: {origin} ({info['size']} bytes) - date: {info['date']} ")
        for j, part in enumerate(info['parts']):
            print(f"\tPart {j}: {part['filename']}")

    file = input("[+] Enter the name of file you want to download:").strip()

    if not file_list.get(file):
        print(f"[!] File '{file}' not found in manifest.")
        return
    
    for part in (parts:=file_list[file]["parts"]):
        print(f"[+] Downloading part: {part['filename']}")

        msg = await client.get_messages(CHANNEL_USERNAME, ids=part["message_id"])
        out_path = os.path.join(DEFAULT_DOWNLOADS_DIR, part["filename"])
        await client.download_media(msg, file=out_path)

    print("[✓] Download complete.")

    if len(parts) > 1:
        print(f"[+] Merging {len(parts)} parts into: {file}")
        merge_chunks(os.path.join(DEFAULT_DOWNLOADS_DIR, file), [os.path.join(DEFAULT_DOWNLOADS_DIR, p["filename"]) for p in parts])


def main():
    parser = argparse.ArgumentParser(description="Telegram File Splitter & Storage")
    subparsers = parser.add_subparsers(dest="command")

    sp_upload = subparsers.add_parser("upload", help="Upload files to Telegram")
    sp_upload.add_argument(
        "--dir",
        default=DEFAULT_FILES_DIR,     
        help="Directory containing files to upload (default: %(default)s)"
    )

    subparsers.add_parser("download", help="Download files using manifest")

    args = parser.parse_args()

    if args.command == "upload":
        files = get_files(args.dir)
        for file in files.copy():
            if size:=os.path.getsize(file) > CHUNK_SIZE:
                print(f"[!] File {file} is too large ({size} bytes). Splitting...")
                files.extend(split_file(file))
                files.remove(file)

        async def upload_main():
            async with TelegramClient(SESSION_NAME, API_ID, API_HASH) as client:
                await upload_files(client, files)
        asyncio.run(upload_main())

    elif args.command == "download":
        async def download_main():
            async with TelegramClient(SESSION_NAME, API_ID, API_HASH) as client:
                await download_files(client)
        asyncio.run(download_main())
    
    else:
        parser.print_help()


if __name__ == "__main__":
    main()