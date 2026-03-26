# ⚠️  SECURITY ALERT - API Keys Exposed in Git

## Problem
Your `.env` file containing API keys has been committed to git and is in the repository history.

## Exposed Keys
- **Moonshot API Key**: sk-SXIXZAnw5Qj6NikY3NgOJ9XsiTyXJxDSY8BRcuN7PLz5cK0q
- **Gemini API Key**: AIzaSyBeuupU7bwJZyAWjpA0ZF4W1DJwXKmQTEM
- **OpenAI API Key**: sk-proj-UIA_KpIA-...
- **Qwen API Key**: sk-aeaab486d8ea4b32bdc3d372a8786c43

## Immediate Actions Required

### 1. Remove .env from Git Tracking (DO THIS NOW)
```bash
# Stop tracking .env (but keep the file locally)
git rm --cached .env

# Verify .env is in .gitignore
grep "^\.env$" .gitignore || echo ".env" >> .gitignore

# Commit the removal
git add .gitignore
git commit -m "security: Remove .env from git tracking"
```

### 2. Rotate ALL API Keys (DO THIS IMMEDIATELY)
**You MUST rotate these keys as they are now public in git history:**

- [ ] **Moonshot**: https://platform.moonshot.cn/console/api-keys
- [ ] **Gemini**: https://aistudio.google.com/apikey
- [ ] **OpenAI**: https://platform.openai.com/api-keys
- [ ] **Qwen**: https://dashscope.console.aliyun.com/apiKey

### 3. Update Your Local .env
Copy `.env.example` to `.env` and add your NEW keys:
```bash
cp .env.example .env
# Edit .env with your NEW rotated keys
```

### 4. (Optional) Clean Git History
If this repo is private and you want to remove keys from history:
```bash
# WARNING: This rewrites history - coordinate with team first
git filter-branch --force --index-filter \
  'git rm --cached --ignore-unmatch .env' \
  --prune-empty --tag-name-filter cat -- --all

# Force push to remote (if necessary)
git push origin --force --all
git push origin --force --tags
```

## Prevention
- `.env` is now in `.gitignore` ✅
- Use `.env.example` as template ✅
- Never commit actual API keys to git ✅

## Next Steps
Once you've rotated all keys and removed .env from tracking, you can safely delete this file:
```bash
rm SECURITY_ALERT.md
```
