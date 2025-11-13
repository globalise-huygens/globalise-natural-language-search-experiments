#!/usr/bin/env python3
"""Quick status check for embeddings and database."""

from pathlib import Path
from app_core import list_available_inv_nrs, _embeddings_file, DB_PATH

def main():
    print("🔍 Deployment Readiness Check\n")
    print("=" * 60)
    
    # Check database
    if DB_PATH.exists():
        size_mb = DB_PATH.stat().st_size / (1024 * 1024)
        print(f"✅ Database exists: {DB_PATH}")
        print(f"   Size: {size_mb:.1f} MB")
    else:
        print(f"❌ Database NOT found: {DB_PATH}")
        print(f"   Run: python precompute_embeddings.py")
        return
    
    print()
    
    # Check embeddings
    inv_nrs = list_available_inv_nrs()
    print(f"📋 Found {len(inv_nrs)} inventory numbers")
    
    missing = []
    existing = []
    
    for inv_nr in inv_nrs:
        emb_file = _embeddings_file(inv_nr)
        if emb_file.exists():
            size_mb = emb_file.stat().st_size / (1024 * 1024)
            existing.append((inv_nr, size_mb))
        else:
            missing.append(inv_nr)
    
    if existing:
        print(f"\n✅ Embeddings exist for {len(existing)} inventory numbers:")
        total_size = 0
        for inv_nr, size_mb in existing[:10]:  # Show first 10
            print(f"   {inv_nr}: {size_mb:.1f} MB")
            total_size += size_mb
        if len(existing) > 10:
            print(f"   ... and {len(existing) - 10} more")
        print(f"   Total: {total_size:.1f} MB")
    
    if missing:
        print(f"\n⚠️  Missing embeddings for {len(missing)} inventory numbers:")
        for inv_nr in missing[:10]:  # Show first 10
            print(f"   {inv_nr}")
        if len(missing) > 10:
            print(f"   ... and {len(missing) - 10} more")
        print(f"\n   Run: python precompute_embeddings.py")
    else:
        print(f"\n✅ All embeddings precomputed!")
    
    print("\n" + "=" * 60)
    
    # Total size
    emb_dir = Path("embeddings")
    if emb_dir.exists():
        total = sum(f.stat().st_size for f in emb_dir.glob("*.db"))
        total_mb = total / (1024 * 1024)
        db_mb = DB_PATH.stat().st_size / (1024 * 1024)
        text_dir = Path("text-input")
        text_mb = sum(f.stat().st_size for f in text_dir.glob("*.csv")) / (1024 * 1024)
        
        grand_total = total_mb + db_mb + text_mb
        print(f"\n📊 Total repository data size: {grand_total:.1f} MB")
        print(f"   text-input/: {text_mb:.1f} MB")
        print(f"   text-metadata-sqlite/: {db_mb:.1f} MB")
        print(f"   embeddings/: {total_mb:.1f} MB")
        
        if grand_total > 1000:
            print(f"\n⚠️  WARNING: Size exceeds Streamlit Cloud limit (1GB)")
        else:
            print(f"\n✅ Size OK for Streamlit Cloud (limit: 1GB)")
    
    print("\n" + "=" * 60)
    
    if not missing:
        print("\n🎉 Ready for deployment!")
        print("\nNext steps:")
        print("  1. git add embeddings/ text-metadata-sqlite/")
        print("  2. git commit -m 'Add precomputed data'")
        print("  3. git push")
        print("  4. Deploy to Streamlit Cloud")
    else:
        print(f"\n⚠️  NOT ready - missing {len(missing)} embeddings")
        print("\nNext steps:")
        print("  1. python precompute_embeddings.py")
        print("  2. Re-run this check")

if __name__ == "__main__":
    main()
