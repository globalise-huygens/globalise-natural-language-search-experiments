#!/usr/bin/env python3
"""
Deployment helper script - Interactive menu for common tasks
"""

import os
import sys
from pathlib import Path

def print_header(text):
    print("\n" + "=" * 70)
    print(f"  {text}")
    print("=" * 70)

def check_env():
    """Check if OpenAI API key is set"""
    from dotenv import load_dotenv
    load_dotenv()
    
    if os.getenv("OPENAI_API_KEY"):
        print("✅ OpenAI API key found in environment")
        return True
    else:
        print("❌ OpenAI API key NOT found")
        print("\nPlease create a .env file with:")
        print("OPENAI_API_KEY=your_key_here")
        return False

def check_status():
    """Run the status checker"""
    print_header("Checking Deployment Status")
    os.system("python check_deployment_status.py")

def precompute_all():
    """Run the precompute script"""
    if not check_env():
        return
    
    print_header("Precomputing All Embeddings")
    print("\nThis will:")
    print("  1. Build/update the SQLite database")
    print("  2. Generate FAISS embeddings for all inventory numbers")
    print("  3. Save to embeddings/ directory")
    print("\nThis may take 10-30 minutes and cost ~$1-2 in API calls.")
    
    response = input("\nContinue? (y/n): ")
    if response.lower() == 'y':
        os.system("python precompute_embeddings.py")
    else:
        print("Cancelled.")

def test_local():
    """Run the Streamlit app locally"""
    if not check_env():
        return
    
    print_header("Starting Local Streamlit App")
    print("\nThe app will open in your browser at http://localhost:8501")
    print("Press Ctrl+C to stop the server\n")
    os.system("streamlit run streamlit_app.py")

def git_status():
    """Show git status for deployment files"""
    print_header("Git Status - Deployment Files")
    
    files = [
        "text-metadata-sqlite/",
        "embeddings/",
        ".streamlit/",
        "streamlit_app.py",
        "app_core.py",
        "requirements.txt",
        "DEPLOYMENT.md",
        "README.md",
    ]
    
    print("\nKey files to commit:")
    for f in files:
        path = Path(f)
        if path.exists():
            if path.is_dir():
                size = sum(p.stat().st_size for p in path.rglob("*") if p.is_file())
                size_mb = size / (1024 * 1024)
                print(f"  ✅ {f} ({size_mb:.1f} MB)")
            else:
                size_mb = path.stat().st_size / (1024 * 1024)
                print(f"  ✅ {f} ({size_mb:.2f} MB)")
        else:
            print(f"  ❌ {f} (missing)")
    
    print("\n" + "-" * 70)
    os.system("git status --short")

def show_docs():
    """Show available documentation"""
    print_header("Documentation")
    
    docs = {
        "README.md": "Quick start and project overview",
        "DEPLOYMENT.md": "Complete Streamlit Cloud deployment guide",
        "CHECKLIST.md": "Pre-deployment checklist",
        "DEPLOYMENT_SUMMARY.md": "Summary of deployment implementation",
    }
    
    for doc, desc in docs.items():
        if Path(doc).exists():
            lines = len(Path(doc).read_text().splitlines())
            print(f"\n📄 {doc}")
            print(f"   {desc}")
            print(f"   ({lines} lines)")
    
    print("\n" + "-" * 70)
    print("To read: cat DEPLOYMENT.md | less")
    print("Or open in your editor")

def main_menu():
    """Show interactive menu"""
    while True:
        print_header("VOC Search - Deployment Helper")
        
        print("\nOptions:")
        print("  1. Check deployment status")
        print("  2. Precompute all embeddings")
        print("  3. Test app locally")
        print("  4. Check git status")
        print("  5. Show documentation")
        print("  6. Quick commands reference")
        print("  q. Quit")
        
        choice = input("\nSelect option: ").strip().lower()
        
        if choice == '1':
            check_status()
        elif choice == '2':
            precompute_all()
        elif choice == '3':
            test_local()
        elif choice == '4':
            git_status()
        elif choice == '5':
            show_docs()
        elif choice == '6':
            show_quick_commands()
        elif choice == 'q':
            print("\nGoodbye! 👋")
            break
        else:
            print("\nInvalid option. Please try again.")
        
        input("\n\nPress Enter to continue...")

def show_quick_commands():
    """Show quick command reference"""
    print_header("Quick Commands Reference")
    
    print("""
LOCAL DEVELOPMENT:
  pip install -r requirements.txt          # Install dependencies
  echo "OPENAI_API_KEY=sk-..." > .env     # Set API key
  python check_deployment_status.py       # Check status
  python precompute_embeddings.py         # Generate embeddings
  streamlit run streamlit_app.py          # Test locally

GIT & DEPLOYMENT:
  git add embeddings/ text-metadata-sqlite/  # Stage precomputed data
  git commit -m "Add precomputed data"       # Commit
  git push                                   # Push to GitHub
  
STREAMLIT CLOUD:
  1. Go to share.streamlit.io
  2. New app → select repo
  3. Main file: streamlit_app.py
  4. Deploy!

MONITORING:
  python check_deployment_status.py       # Verify readiness
  git status                              # Check uncommitted files
  du -sh embeddings/ text-metadata-sqlite/  # Check sizes

DOCUMENTATION:
  cat DEPLOYMENT.md                       # Full deployment guide
  cat CHECKLIST.md                        # Pre-deployment checklist
  cat DEPLOYMENT_SUMMARY.md               # Implementation summary
""")

if __name__ == "__main__":
    try:
        main_menu()
    except KeyboardInterrupt:
        print("\n\nInterrupted. Goodbye! 👋")
        sys.exit(0)
