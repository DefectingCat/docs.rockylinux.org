#!/bin/bash

set -e

echo "=== SELF-HOSTED BUILD ==="

# Record project root directory before any directory changes
PROJECT_ROOT="$(pwd)"

# Install dependencies into a virtual environment
echo "Creating virtual environment and installing dependencies..."
uv venv --python 3.12 .venv
uv pip install -r requirements.txt

# Add venv bin to PATH so mike/mkdocs are found directly
export PATH="$(pwd)/.venv/bin:$PATH"

echo "Virtual environment created and added to PATH"

# Patch privacy plugin for better reliability (timeout + retries)
echo "Patching privacy plugin for offline deployment..."
./scripts/patch_privacy_plugin.py .venv

# FORCE cleanup of build artifacts (but preserve local documentation repos)
echo "Force cleaning build artifacts (preserving rockydocs-* for incremental updates)..."
rm -rf docs site 2>/dev/null || true

# Create privacy plugin cache directory for offline deployment
echo "Setting up offline deployment cache..."
mkdir -p "$PROJECT_ROOT/.cache/privacy"

# Create isolated build directory for git init and mike operations
# Cloned repos go to project root, but git/mike state stays isolated
BUILD_DIR=$(mktemp -d)
echo "Created isolated build directory: $BUILD_DIR"

# Cleanup trap: only removes the temporary build directory on exit
trap 'echo "Cleaning up build directory: $BUILD_DIR"; rm -rf "$BUILD_DIR"' EXIT

# Change to build directory for all git/mike operations
pushd "$BUILD_DIR"

# Function to build a specific version from a specific branch
build_version() {
    local version=$1
    local branch=$2
    local alias=$3
    local title=$4

    echo "Building Rocky Linux $version from branch $branch..."

    # Clone the specific branch WITH FULL HISTORY for git-revision-date-localized-plugin
    # Use incremental update if local repo already exists
    local repo_dir="rockydocs-$version"
    local repo_path="$PROJECT_ROOT/$repo_dir"

    if [ -d "$repo_path/.git" ]; then
        echo "Found existing local repo at $repo_path, updating..."
        pushd "$repo_path"
        git checkout "$branch" 2>/dev/null || { echo "ERROR: Branch $branch not found in local repo"; popd; return 1; }
        git pull origin "$branch"
        popd
        echo "Local repo updated successfully"
    else
        echo "No local repo found, cloning $branch with full git history to $repo_path..."
        git clone -b "$branch" https://github.com/rocky-linux/documentation.git "$repo_path"
        echo "Clone completed"
    fi

    # Verify update/clone worked
    if [ ! -d "$repo_path/.git" ]; then
        echo "ERROR: Failed to clone/update $branch branch"
        return 1
    fi

    echo "Working with local repo at $repo_path"

    # Create a symlink to preserve git history access
    rm -rf docs
    ln -sf "$repo_path/docs" docs
    rm -rf include
    ln -sf "$repo_path/include" include
    rm -rf theme
    ln -sf "$PROJECT_ROOT/theme" theme
    rm -rf .cache
    ln -sf "$PROJECT_ROOT/.cache" .cache

    # Ensure mkdocs.yml is available for mike operations
    if [ ! -f "mkdocs.yml" ]; then
        ln -sf "$PROJECT_ROOT/configs/mkdocs.yml" mkdocs.yml
    fi

    echo "Created symlink to docs with preserved git history"

    # Initialize git repo in build dir (isolated from project .git)
    if [ ! -d ".git" ]; then
        git init
        git config user.name "wsoyinka"
        git config user.email "webmaster@rockylinux.org"

        # Add the documentation repo as a worktree/submodule reference
        git add .
        git commit -m "Build commit for version $version $(date)"
    fi

    echo "Deploying version $version with preserved git history"
    if [ -n "$alias" ] && [ -n "$title" ]; then
        mike deploy "$version" "$alias" --title="$title"
    elif [ -n "$alias" ]; then
        mike deploy "$version" "$alias"
    elif [ -n "$title" ]; then
        mike deploy "$version" --title="$title"
    else
        mike deploy "$version"
    fi

    echo "Rocky Linux $version deployed successfully with git history preserved"
}

echo "Starting git-aware build process..."

# Set up initial git repo for mike operations (in isolated build directory only)
git init
git config user.name "wsoyinka"
git config user.email "webmaster@rockylinux.org"

# Create initial commit
echo "# Rocky Linux Docs Build" > README.md
git add README.md
git commit -m "Initial commit for self-hosted build $(date)"

# Build each version from its respective branch
build_version "8" "rocky-8" "" ""
build_version "9" "rocky-9" "" ""
build_version "10" "main" "latest" ""

echo "Setting default version..."
mike set-default latest

echo "All versions deployed successfully"

# Verify mike state
echo "Verifying mike deployment..."
mike list

echo "Extracting built site for local deployment with ROOT + VERSIONED deployment..."

# Clean any existing site directory in the project root
rm -rf "$PROJECT_ROOT/site"

# Extract from gh-pages for local deployment
if git show-ref --verify --quiet refs/heads/gh-pages; then
    echo "gh-pages branch found"

    BRANCH_FILE_COUNT=$(git ls-tree --name-only gh-pages | wc -l)
    echo "Files in gh-pages branch: $BRANCH_FILE_COUNT"

    if [ "$BRANCH_FILE_COUNT" -gt 0 ]; then
        echo "Extracting site content from gh-pages..."

        mkdir -p site
        git archive gh-pages | tar -x -C site

        if [ -d "site" ] && [ "$(ls -A site 2>/dev/null | wc -l)" -gt 0 ]; then
            echo "Site extracted successfully for local deployment"
            echo "Site contents:"
            ls -la site/ | head -10

            # NEW V21 FEATURE: Deploy latest version to root for backward compatibility
            echo ""
            echo "V21 FEATURE: Deploying latest version to ROOT for backward compatibility..."

            # Check if latest version directory exists in the extracted site
            if [ -d "site/latest" ]; then
                echo "Found latest version directory"

                # Copy latest version content to root, but preserve versioned structure
                echo "Copying latest version content to root..."

                # First, backup the version selector and other mike-generated files
                if [ -f "site/versions.json" ]; then
                    cp site/versions.json site/versions.json.backup
                    echo "Backed up versions.json"
                fi

                # Copy latest content to root (excluding version-specific metadata)
                # Use cp instead of rsync (not available in Vercel environment)
                cp -r site/latest/* site/ 2>/dev/null || true

                # Restore the versions.json to maintain version selector functionality
                if [ -f "site/versions.json.backup" ]; then
                    cp site/versions.json.backup site/versions.json
                    rm site/versions.json.backup
                    echo "Restored versions.json for version selector"
                fi

                # Ensure version directories are still accessible
                echo "Verifying versioned access..."
                if [ -d "site/8" ] && [ -d "site/9" ] && [ -d "site/10" ]; then
                    echo "Versioned directories (8, 9, 10) are accessible"
                else
                    echo "WARNING: Some versioned directories may be missing"
                fi

                # Verify root content
                if [ -f "site/index.html" ]; then
                    echo "Root index.html exists (latest content)"
                else
                    echo "ERROR: Root index.html missing!"
                    exit 1
                fi

                echo ""
                echo "ROOT + VERSIONED deployment successful!"
                echo "Access patterns:"
                echo "   • docs.rockylinux.org/          → Rocky Linux 10 (latest)"
                echo "   • docs.rockylinux.org/latest/   → Rocky Linux 10"
                echo "   • docs.rockylinux.org/10/       → Rocky Linux 10"
                echo "   • docs.rockylinux.org/9/        → Rocky Linux 9"
                echo "   • docs.rockylinux.org/8/        → Rocky Linux 8"

            else
                echo "ERROR: Latest version directory not found in site!"
                echo "Available directories:"
                ls -la site/
                exit 1
            fi
        else
            echo "ERROR: Site extraction failed"
            exit 1
        fi
    else
        echo "ERROR: gh-pages branch is empty!"
        exit 1
    fi
else
    echo "ERROR: No gh-pages branch found!"
    exit 1
fi

# Copy the built site back to the project root
echo "Copying built site to project root: $PROJECT_ROOT/site"
cp -r site "$PROJECT_ROOT/site"

echo ""
echo "Self-hosted build completed successfully!"
echo "Features:"
echo "   • Backward compatibility: Latest content served from root"
echo "   • Version selector: Still works from any page"
echo "   • Existing bookmarks: Will continue to work"
echo "   • Versioned access: All versions accessible via /8/, /9/, /10/, /latest/"
echo "   • Git history: Preserved for accurate timestamps"
echo "   • OFFLINE DEPLOYMENT: All CDN resources downloaded locally"
echo ""
echo "Build output location: $PROJECT_ROOT/site/"
echo ""
echo "To preview locally:"
echo "  cd $PROJECT_ROOT"
echo "  python3 -m http.server --directory site"
echo ""
echo "Cloned documentation repos (preserved for incremental updates):"
ls -d "$PROJECT_ROOT"/rockydocs-* 2>/dev/null | sed 's/^/  - /'
echo ""
echo "Tip: Subsequent runs will use 'git pull' for fast incremental updates"
