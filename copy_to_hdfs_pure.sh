#!/usr/bin/env bash

# Script to copy all data and metadata files to HDFS path
# Pure bash/unix version - NO Python or jq required
# Usage: ./copy_to_hdfs_pure.sh <source_config.json> <hdfs_destination_path>

set -e

# Logger function
logger() {
    printf '%s %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*"
}

# Check if required arguments are provided
if [ $# -lt 2 ]; then
    logger "ERROR: Missing required arguments"
    logger "Usage: $0 <source_config.json> <hdfs_destination_path>"
    logger "Example: $0 conf.json /hdfs/path/to/destination"
    exit 1
fi

CONFIG_FILE="$1"
HDFS_DEST="$2"

# Validate config file exists
if [ ! -f "$CONFIG_FILE" ]; then
    logger "ERROR: Configuration file not found: $CONFIG_FILE"
    exit 1
fi

# Check if hdfs command is available
if ! command -v hdfs &> /dev/null; then
    logger "ERROR: hdfs command not found. Please ensure Hadoop is installed and hdfs is in PATH"
    exit 1
fi

logger "Starting copy of data and metadata files to HDFS"
logger "Config file: $CONFIG_FILE"
logger "HDFS destination: $HDFS_DEST"

# Create destination directory in HDFS
logger "Creating HDFS destination directory: $HDFS_DEST"
hdfs dfs -mkdir -p "$HDFS_DEST"

# Extract files using sed and grep (pure bash/unix)
FILES_TO_COPY=""

# Extract all quoted strings that look like file paths
# This regex looks for "file": "path" and "metadata": "path" patterns
while IFS= read -r line; do
    # Extract paths after "file": and "metadata":
    if [[ $line =~ \"(file|metadata)\"[[:space:]]*:[[:space:]]*\"([^\"]+)\" ]]; then
        file_path="${BASH_REMATCH[2]}"
        
        # Expand glob patterns using shell expansion
        # Use eval to expand wildcards safely
        for expanded_file in $(eval echo "$file_path"); do
            # Only add if file exists or if it's a literal path
            if [ -f "$expanded_file" ]; then
                # Check if already in list to avoid duplicates
                if ! echo "$FILES_TO_COPY" | grep -F -x "$expanded_file" > /dev/null 2>&1; then
                    FILES_TO_COPY=$(printf '%s\n%s' "$FILES_TO_COPY" "$expanded_file")
                fi
            else
                # Add pattern even if file doesn't exist yet (for logging)
                if ! echo "$FILES_TO_COPY" | grep -F -x "$file_path" > /dev/null 2>&1; then
                    FILES_TO_COPY=$(printf '%s\n%s' "$FILES_TO_COPY" "$file_path")
                fi
            fi
        done
    fi
done < <(grep -E '"(file|metadata)"' "$CONFIG_FILE")

if [ -z "$FILES_TO_COPY" ]; then
    logger "WARNING: No files found in configuration"
fi

# Count total files
FILE_COUNT=$(echo "$FILES_TO_COPY" | grep -c . || echo 0)
logger "Found $FILE_COUNT file(s) to copy"

# Copy files to HDFS
COPIED_COUNT=0
FAILED_COUNT=0

while IFS= read -r file; do
    [ -z "$file" ] && continue
    
    if [ -f "$file" ]; then
        logger "Copying: $file"
        if hdfs dfs -copyFromLocal -f "$file" "$HDFS_DEST/"; then
            logger "✓ Successfully copied: $file"
            ((COPIED_COUNT++))
        else
            logger "✗ Failed to copy: $file"
            ((FAILED_COUNT++))
        fi
    else
        logger "✗ File not found (skipping): $file"
        ((FAILED_COUNT++))
    fi
done <<< "$FILES_TO_COPY"

# Summary
logger "=========================================="
logger "Copy operation completed"
logger "Successfully copied: $COPIED_COUNT file(s)"
logger "Failed/Skipped: $FAILED_COUNT file(s)"
logger "HDFS destination: $HDFS_DEST"
logger "=========================================="

if [ $FAILED_COUNT -gt 0 ]; then
    exit 1
fi

exit 0