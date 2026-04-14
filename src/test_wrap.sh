#!/bin/bash

# =========================
# Global variables
# =========================
declare -a processedHdfsDirs=()
declare -a copiedFiles=()

batchCount=1
batchDir=""

fid="$(whoami)"
year="$(date '+%Y')"
month="$(date '+%m')"
day="$(date '+%d')"

logger "fid: $fid"
logger "year: $year"
logger "month: $month"
logger "day: $day"

# =========================
# Validation
# =========================
if [[ -z "$STATIC_SPARK_ARGS" ]]; then
    err_msg="Error: STATIC_SPARK_ARGS is empty"
    logger "$err_msg"
    spark_audit_call "$err_msg"
    cust_exit 1
fi

file_read_cfg="$(printf '%s' "$STATIC_SPARK_ARGS" | jq -r '.file_read_cfg')"

if [[ -z "$file_read_cfg" || "$file_read_cfg" == "null" ]]; then
    err_msg="Error: file_read_cfg is missing in STATIC_SPARK_ARGS"
    logger "$err_msg"
    spark_audit_call "$err_msg"
    cust_exit 1
fi

# =========================
# Find JSON file from FILES_TO_CLUSTER
# =========================
json_file=""
IFS=',' read -r -a file_array <<< "$FILES_TO_CLUSTER"

for file_path in "${file_array[@]}"; do
    if [[ "$file_path" == *"$file_read_cfg"* ]]; then
        json_file="$file_path"
        break
    fi
done

if [[ -z "$json_file" ]]; then
    err_msg="Error: Could not find JSON file matching file_read_cfg: $file_read_cfg in FILES_TO_CLUSTER"
    logger "$err_msg"
    spark_audit_call "$err_msg"
    cust_exit 1
fi

if [[ ! -f "$json_file" ]]; then
    err_msg="Error: JSON file not found at $json_file"
    logger "$err_msg"
    spark_audit_call "$err_msg"
    cust_exit 1
fi

logger "Using JSON file: $json_file"

# =========================
# Functions
# =========================
getBatchFolder() {
    local currentBatchDir

    while true; do
        currentBatchDir="$hdfsDir/batch$batchCount"

        hdfs dfs -test -d "$currentBatchDir"
        if [[ $? -ne 0 ]]; then
            batchDir="$currentBatchDir"
            logger "Using batch directory: $batchDir"
            return 0
        fi

        batchCount=$((batchCount + 1))
    done
}

processHdfsDirectory() {
    local hdfsDirLocal="$1"
    local alreadyProcessed=false
    local existing

    for existing in "${processedHdfsDirs[@]}"; do
        if [[ "$existing" == "$hdfsDirLocal" ]]; then
            alreadyProcessed=true
            break
        fi
    done

    if [[ "$alreadyProcessed" == false ]]; then
        processedHdfsDirs+=("$hdfsDirLocal")
        hdfsDir="$hdfsDirLocal"
        getBatchFolder
        return 0
    else
        logger "HDFS Directory already processed: $hdfsDirLocal"

        batchDir="$(hdfs dfs -ls "$hdfsDirLocal" 2>/dev/null | awk '{print $NF}' | grep '/batch[0-9]\+$' | sort | tail -n 1)"

        if [[ -z "$batchDir" ]]; then
            err_msg="Error: No existing batch directory found under $hdfsDirLocal"
            logger "$err_msg"
            spark_audit_call "$err_msg"
            cust_exit 1
        fi

        logger "Using latest existing batch directory: $batchDir"
        return 1
    fi
}

copyToBatchDirectory() {
    local targetBatchDir="$1"
    local filePattern="$2"
    local metadataFile="$3"
    local fileType="$4"
    local matched=false
    local file_path

    hdfs dfs -test -d "$targetBatchDir"
    if [[ $? -ne 0 ]]; then
        logger "Creating batch directory: $targetBatchDir"
        hdfs dfs -mkdir -p "$targetBatchDir"
        if [[ $? -ne 0 ]]; then
            err_msg="Error creating HDFS batch directory: $targetBatchDir"
            logger "$err_msg"
            spark_audit_call "$err_msg"
            cust_exit 1
        fi
    fi

    logger "Copying data file(s) to HDFS: $filePattern -> $targetBatchDir"
    hdfs dfs -put -f $filePattern "$targetBatchDir/"
    if [[ $? -ne 0 ]]; then
        err_msg="Error copying file(s) to HDFS: $filePattern"
        logger "$err_msg"
        spark_audit_call "$err_msg"
        cust_exit 1
    fi

    for file_path in $filePattern; do
        [[ -e "$file_path" ]] || continue
        copiedFiles+=("$file_path")
        logger "Successfully copied file: $file_path"
        matched=true
    done

    if [[ "$matched" == false ]]; then
        logger "Warning: no local files matched pattern: $filePattern"
    fi

    if [[ "$fileType" != "parquet" ]]; then
        if [[ -n "$metadataFile" && "$metadataFile" != "null" ]]; then
            logger "Copying metadata to HDFS: $metadataFile -> $targetBatchDir"
            hdfs dfs -put -f "$metadataFile" "$targetBatchDir/"
            if [[ $? -ne 0 ]]; then
                err_msg="Error copying metadata to HDFS: $metadataFile"
                logger "$err_msg"
                spark_audit_call "$err_msg"
                cust_exit 1
            fi
        fi
    fi
}

# =========================
# Main processing
# =========================
OLDIFS="$IFS"
IFS=$'\n'

for obj_b64 in $(jq -r --arg key "$ENV" '.[$key][] | @base64' "$json_file"); do
    obj="$(printf '%s' "$obj_b64" | base64 --decode)"

    logger "Processing object: $obj"

    file="$(printf '%s' "$obj" | jq -r 'if .file | type == "object" then .file.file else .file end')"
    metadata="$(printf '%s' "$obj" | jq -r 'if .file | type == "object" then .file.metadata else .metadata end')"
    csi="$(printf '%s' "$obj" | jq -r '.csi')"
    appName="$(printf '%s' "$obj" | jq -r '.appName')"
    fileType="$(printf '%s' "$obj" | jq -r '.fileType // "delimited"')"

    if [[ -z "$file" || "$file" == "null" ]]; then
        err_msg="Error: file is missing in object: $obj"
        logger "$err_msg"
        spark_audit_call "$err_msg"
        cust_exit 1
    fi

    if [[ -z "$csi" || "$csi" == "null" ]]; then
        err_msg="Error: csi is missing in object: $obj"
        logger "$err_msg"
        spark_audit_call "$err_msg"
        cust_exit 1
    fi

    if [[ -z "$appName" || "$appName" == "null" ]]; then
        err_msg="Error: appName is missing in object: $obj"
        logger "$err_msg"
        spark_audit_call "$err_msg"
        cust_exit 1
    fi

    if [[ "$fileType" != "parquet" && ( -z "$metadata" || "$metadata" == "null" ) ]]; then
        err_msg="Error: metadata is required for non-parquet fileType '$fileType' in object: $obj"
        logger "$err_msg"
        spark_audit_call "$err_msg"
        cust_exit 1
    fi

    logger "file     : $file"
    logger "metadata : $metadata"
    logger "csi      : $csi"
    logger "appName  : $appName"
    logger "fileType : $fileType"

    hdfsDir="/data/$fid/$csi/$appName/$year/$month/$day"
    logger "HDFS directory: $hdfsDir"

    processHdfsDirectory "$hdfsDir"
    logger "Batch HDFS directory: $batchDir"

    copyToBatchDirectory "$batchDir" "$file" "$metadata" "$fileType"
done

IFS="$OLDIFS"

# =========================
# Final logging
# =========================
logger "Processed HDFS directories count: ${#processedHdfsDirs[@]}"
logger "Copied files count: ${#copiedFiles[@]}"

if [[ ${#copiedFiles[@]} -eq 0 ]]; then
    logger "Warning: copiedFiles array is empty. No files copied."
else
    logger "Copied files list:"
    for f in "${copiedFiles[@]}"; do
        logger "  $f"
    done
fi

logger "All objects processed successfully."