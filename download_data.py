import os
from pathlib import Path
import requests
from tqdm import tqdm
import zipfile
import shutil

def download_file(url, dest_path):
    """Download file from URL to destination path with progress bar."""
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Check if file already exists
    if dest_path.exists():
        print(f"✅ File already exists: {dest_path}")
        return
    
    print(f"📥 Downloading {dest_path.name}...")
    
    response = requests.get(url, stream=True, allow_redirects=True)
    response.raise_for_status()
    
    total_size = int(response.headers.get('content-length', 0))
    
    with open(dest_path, 'wb') as f:
        if total_size == 0:
            f.write(response.content)
        else:
            with tqdm(total=total_size, unit='B', unit_scale=True) as pbar:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
                    pbar.update(len(chunk))
    
    print(f"✅ Downloaded {dest_path}")

def extract_zip(zip_path, extract_to="."):
    """Extract ZIP file to specified directory."""
    print(f"📦 Extracting {zip_path.name}...")
    
    with zipfile.ZipFile(zip_path, 'r') as zip_ref:
        # Get list of files
        file_list = zip_ref.namelist()
        print(f"   Found {len(file_list)} files in archive")
        
        # Extract with progress bar
        for file in tqdm(file_list, desc="Extracting"):
            zip_ref.extract(file, extract_to)
    
    print(f"✅ Extracted to {extract_to}")

# Define your cloud storage URLs for ZIP files
ZIP_FILES_TO_DOWNLOAD = {
    # Replace SHARECODE with your actual share code
    "https://surfdrive.surf.nl/files/index.php/s/8edwicW2DYd8QAB/download": 
        ("voc-search-data.zip", "."),
}

def ensure_data_files():
    """Download and extract ZIP files if they don't exist locally."""
    if not ZIP_FILES_TO_DOWNLOAD:
        print("⚠️  No files configured for download. Update ZIP_FILES_TO_DOWNLOAD in download_data.py")
        return
    
    print(f"🔍 Processing {len(ZIP_FILES_TO_DOWNLOAD)} data archive(s)...")
    
    for url, (zip_dest, extract_to) in ZIP_FILES_TO_DOWNLOAD.items():
        zip_path = Path(zip_dest)
        extract_path = Path(extract_to)
        
        try:
            # Download ZIP if it doesn't exist
            download_file(url, zip_path)
            
            # Extract ZIP
            extract_zip(zip_path, extract_to)
            
            # Clean up ZIP file after extraction
            print(f"🗑️  Removing temporary ZIP file...")
            zip_path.unlink()
            
        except Exception as e:
            print(f"❌ Error processing {zip_dest}: {e}")
            # Clean up partial ZIP if it exists
            if zip_path.exists():
                zip_path.unlink()
            raise
    
    print("✅ All data files ready!")

if __name__ == "__main__":
    # Can be run standalone for testing
    ensure_data_files()