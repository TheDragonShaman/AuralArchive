# Development Workflow

This document outlines the development workflow for AuralArchive.

## Branch Structure

- **`main`**: Production-ready releases only
- **`dev`**: Active development branch

## Development Workflow

### 1. Daily Development
- Always work on the `dev` branch
- Make regular commits with descriptive messages
- Push changes to `origin dev` regularly

```bash
# Check current branch
git branch

# Make sure you're on dev
git checkout dev

# Pull latest changes
git pull origin dev

# Make your changes...

# Stage and commit changes
git add .
git commit -m "Descriptive commit message"

# Push to dev branch
git push origin dev
```

### 2. Creating Production Releases

Only when ready for a production release:

```bash
# Switch to main branch
git checkout main

# Pull latest main (if any)
git pull origin main

# Merge dev into main
git merge dev

# Push to main
git push origin main

# Switch back to dev for continued development
git checkout dev
```

### 3. Feature Development

For larger features, you can create feature branches:

```bash
# Create and switch to feature branch from dev
git checkout dev
git checkout -b feature/new-feature-name

# Work on your feature...
git add .
git commit -m "Add new feature"

# Push feature branch
git push origin feature/new-feature-name

# When complete, merge back to dev
git checkout dev
git merge feature/new-feature-name

# Clean up feature branch
git branch -d feature/new-feature-name
git push origin --delete feature/new-feature-name
```

## Commit Message Guidelines

Use clear, descriptive commit messages:

- `feat: add new search functionality`
- `fix: resolve database connection issue`
- `docs: update API documentation`
- `style: improve CSS styling`
- `refactor: optimize database queries`
- `test: add unit tests for search`

## Security Reminders

- Never commit sensitive data (passwords, API keys, etc.)
- Always check `.gitignore` is working properly
- Use environment variables for configuration
- Review changes before committing

## Current Setup Status

✅ **Completed:**
- Local repository initialized
- Connected to GitHub repository
- `dev` branch created and active
- `.gitignore` configured to exclude sensitive files
- Initial codebase committed and pushed to `dev`

✅ **Next Steps:**
- Continue development on `dev` branch
- When ready for production: merge `dev` → `main`
