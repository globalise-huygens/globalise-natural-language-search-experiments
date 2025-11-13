# Pre-Deployment Checklist

Before deploying to Streamlit Cloud, complete these steps:

## ✅ Local Preparation

- [ ] **Set up environment**
  ```bash
  pip install -r requirements.txt
  echo "OPENAI_API_KEY=your_key_here" > .env
  ```

- [ ] **Precompute all embeddings**
  ```bash
  python precompute_embeddings.py
  ```
  Expected output:
  - `text-metadata-sqlite/voc_documents.db` (~96MB)
  - `embeddings/*.db` (one per inventory number, ~109MB total)

- [ ] **Test locally**
  ```bash
  streamlit run streamlit_app.py
  ```
  - Verify: API key input works (sidebar)
  - Verify: Search returns results
  - Verify: CSV download works
  - Verify: No "Database rebuild" option visible (cloud mode detection)

## 📦 Git Repository

- [ ] **Check file structure**
  ```bash
  git status
  ```
  
  Should include:
  - ✅ `text-metadata-sqlite/voc_documents.db`
  - ✅ `embeddings/*.db` (all inventory numbers)
  - ✅ `.streamlit/config.toml`
  - ✅ `requirements.txt`
  - ✅ `streamlit_app.py`
  - ✅ `app_core.py`
  - ✅ `DEPLOYMENT.md`
  - ✅ `README.md`
  
  Should NOT include:
  - ❌ `.env` (excluded by .gitignore)
  - ❌ `results/*.csv` (excluded by .gitignore)

- [ ] **Commit precomputed data**
  ```bash
  git add text-metadata-sqlite/ embeddings/ .streamlit/
  git commit -m "Add precomputed embeddings and database for deployment"
  git push origin main
  ```

- [ ] **Verify repo size**
  - Total size should be ~232MB (well under 1GB limit)
  - Check on GitHub: Settings → General → Repository size

## ☁️ Streamlit Cloud Setup

- [ ] **Create Streamlit Cloud account**
  - Go to https://share.streamlit.io
  - Sign in with GitHub

- [ ] **Deploy app**
  1. Click "New app"
  2. Select your repository
  3. Branch: `main` (or your default branch)
  4. Main file path: `streamlit_app.py`
  5. Click "Deploy"

- [ ] **Wait for deployment**
  - Initial build: 2-5 minutes
  - Watch logs for errors

- [ ] **Test deployed app**
  - Open the Streamlit Cloud URL
  - Enter a test API key
  - Run a search query
  - Verify results appear
  - Download CSV and check contents

## 🔒 Security Verification

- [ ] **API key handling**
  - Confirm: No default API key visible in sidebar
  - Confirm: API key field is `type="password"` (shows dots)
  - Confirm: Help text mentions "never saved"
  - Confirm: API key clears after closing browser

- [ ] **Cloud mode restrictions**
  - Confirm: "Database rebuild" option NOT visible on Streamlit Cloud
  - Confirm: Info message says "Database en embeddings zijn vooraf berekend"
  - Confirm: Search works without needing to create new embeddings

- [ ] **Data privacy**
  - Confirm: `.env` file NOT in repository
  - Confirm: `results/*.csv` files NOT in repository
  - Confirm: No hardcoded API keys in any Python files

## 👥 Team Onboarding

- [ ] **Share app URL**
  - Get URL from Streamlit Cloud dashboard
  - Share with team members

- [ ] **Provide user instructions**
  - Share the "User Instructions" section from DEPLOYMENT.md
  - Explain API key requirements
  - Share cost estimates

- [ ] **Document support process**
  - Where to report issues
  - How to request new inventory numbers
  - Contact for questions

## 🔄 Future Updates

- [ ] **Adding new inventory numbers**
  1. Add CSV to `text-input/`
  2. Run `python precompute_embeddings.py`
  3. Commit and push updated `embeddings/` and `text-metadata-sqlite/`
  4. Streamlit auto-redeploys

- [ ] **Changing chunking parameters**
  1. Update defaults in `app_core.py` or `precompute_embeddings.py`
  2. Delete `text-metadata-sqlite/voc_documents.db` and `embeddings/*.db`
  3. Run `python precompute_embeddings.py`
  4. Commit and push

## 📊 Monitoring

- [ ] **Set up usage tracking** (optional)
  - Monitor Streamlit Cloud usage dashboard
  - Track OpenAI API usage per user (they use their own keys)
  - Set up alerts for app downtime

- [ ] **Performance checks**
  - Test with multiple concurrent users
  - Monitor memory usage (Streamlit Cloud dashboard)
  - Optimize if needed (caching, smaller embeddings)

## ✨ Post-Deployment

- [ ] Update team documentation with live URL
- [ ] Create FAQ based on user questions
- [ ] Consider adding analytics (optional)
- [ ] Plan regular data updates schedule

---

## Common Issues & Solutions

### "Module not found" on Streamlit Cloud
- **Solution**: Check `requirements.txt` has all dependencies
- Run `pip freeze > requirements.txt` locally

### "Embeddings not found" error
- **Solution**: Ensure `embeddings/` folder is committed to git
- Re-run `python precompute_embeddings.py` and commit

### App is slow/crashes
- **Solution**: Check Streamlit Cloud resource limits
- Consider upgrading tier or optimizing FAISS indexes

### Users can't enter API key
- **Solution**: Verify session state initialization in `streamlit_app.py`
- Check browser console for JavaScript errors

---

**Last updated:** November 2025
