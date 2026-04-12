# Release Process

This project uses GitHub Actions to automatically build and publish releases.

## Creating a Release

### Method 1: Tag Push (Recommended)

1. **Create a tag locally:**
   ```bash
   git tag v1.0.0
   git push origin v1.0.0
   ```

2. **GitHub Actions will automatically:**
   - ✅ Detect the tag push
   - ✅ Create an archive excluding unnecessary files
   - ✅ Create a GitHub release with the archive attached

3. **Download from GitHub Releases:**
   - Go to your repository
   - Click **Releases** in the sidebar
   - Find your version and download `LMStudioBot-v1.0.0.zip`

### Method 2: Manual Workflow Dispatch

1. **Go to GitHub Actions:**
   - Navigate to your repository on GitHub
   - Click **Actions** tab
   - Select **Build and Release** workflow on the left

2. **Run workflow:**
   - Click **Run workflow** (top right)
   - Enter tag name (e.g., `v1.0.0`)
   - Click **Run workflow**

3. **Download:**
   - Wait for workflow to complete
   - Go to **Releases** to download the archive

## Version Naming Convention

Use semantic versioning: `v{MAJOR}.{MINOR}.{PATCH}`

Examples:
- `v1.0.0` - First release
- `v1.1.0` - Minor feature release
- `v1.0.1` - Patch/bug fix release
- `v2.0.0-beta` - Pre-release

## What's In The Release Archive

### ✅ Included
- `src/` - All source code
- `tests/` - All test files
- `README.md` - Main documentation
- `.env.example` - Configuration template
- `launch.bat`, `launch.sh` - Setup/launch scripts
- `requirements.txt` - Python dependencies

### ❌ Excluded (To Keep Archive Small & Clean)
- `.venv/` - Virtual environment (users create their own)
- `specs/`, `*.md` - Documentation & specs (only README.md kept)
- `__pycache__/`, `.pytest_cache/` - Python cache
- `.git/`, `.github/` - Git history & workflows
- `.env` - Sensitive environment variables
- `.vscode/`, `.idea/` - IDE configurations
- `dist/`, `build/` - Build artifacts
- `.gitignore`, `.editorconfig` - Git/editor configs

## CI/CD Workflow Details

The `release.yml` workflow:

1. **Triggers on:**
   - Push to any tag starting with `v` (e.g., `v1.0.0`)
   - Manual workflow dispatch

2. **Builds:**
   - Checks out code
   - Creates a ZIP archive with proper exclusions
   - Preserves directory structure

3. **Releases:**
   - Creates GitHub release with detailed notes
   - Attaches the ZIP archive
   - Makes it immediately downloadable

## Checking Workflow Status

1. Go to **Actions** tab on GitHub
2. Select **Build and Release** workflow
3. Check the latest run status
4. Click to see logs if needed

## Troubleshooting

### Archive missing from release
- Check workflow logs in **Actions** tab
- Ensure tag name follows `v*` pattern
- Verify workflow has permission to create releases

### Release not created
- Check that GitHub Actions is enabled in repo settings
- Verify tag was pushed to correct repository
- Check Actions tab for error logs

### Need to recreate a release
1. Delete the tag locally: `git tag -d v1.0.0`
2. Delete the tag on GitHub: `git push origin :v1.0.0`
3. Delete the release on GitHub (Releases page)
4. Tag and push again

## Downloading Archives

Users can download releases from:
- **GitHub Web UI:** Repository → Releases → Select version → Download `.zip`
- **Direct Link:** 
  ```
  https://github.com/yourusername/LMStudioBot/releases/download/v1.0.0/LMStudioBot-v1.0.0.zip
  ```
- **Command line:**
  ```bash
  wget https://github.com/yourusername/LMStudioBot/releases/download/v1.0.0/LMStudioBot-v1.0.0.zip
  ```

---

For more info, see `.github/workflows/release.yml`
