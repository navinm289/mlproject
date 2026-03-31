#!/usr/bin/env bash

# This script requires below arguments
# 1. Environment - Mandatory
# 2. Shell wrapper conf - Mandatory

LOGGER_UTILS_PATH="${LOGGER_UTILS_PATH:-/deploy/app/169912_Foundation/Shared_Libraries/logger_utils/logger.sh}"
KRB_UTILS_PATH="${KRB_UTILS_PATH:-/deploy/app/169912_Foundation/Shared_Libraries/kerberos_utils/krb_utils.sh}"
SPARK_SUBMIT_BIN="${SPARK_SUBMIT_BIN:-spark3-submit}"

if [ -f "$LOGGER_UTILS_PATH" ]; then
    # shellcheck disable=SC1090
    . "$LOGGER_UTILS_PATH"
fi

if [ "$(type -t logger 2>/dev/null)" != "function" ]; then
    logger() {
        printf '%s %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*"
    }
fi

if [ -f "$KRB_UTILS_PATH" ]; then
    # shellcheck disable=SC1090
    . "$KRB_UTILS_PATH"
fi

if [ "$(type -t krb_init 2>/dev/null)" != "function" ]; then
    krb_init() {
        return 0
    }
fi

if [ "$(type -t krb_destroy 2>/dev/null)" != "function" ]; then
    krb_destroy() {
        return 0
    }
fi

if [ "$(type -t spark_audit_call 2>/dev/null)" != "function" ]; then
    spark_audit_call() {
        return 0
    }
fi

uuid=$(uuidgen 2>/dev/null || date '+%s')
FID=$(whoami)

ENV=""
env=""
wrapperConf=""
audit_pipeline_id=""
MAIN_JAR=""
KEYSTORE=""
TRUSTSTORE=""
KEYTAB=""
PRINCIPAL=""
SPARK_JAR_LIST=""
SPARK_FILE_LIST=""
LOG4J_FILE_DRIVER=""
LOG4J_FILE_EXECUTOR=""

additional_args=()
PARSED_SHELL_WORDS=()
CUSTOM_SPARK_FILE_ITEMS=()
SPARK_CONF_OPTS=()

usage() {
    logger "Usage: $0 -e <env> -c <config> [additional spark args]"
}

join_by_comma() {
    local IFS=","
    printf '%s' "$*"
}

python_tokenizer() {
    local raw_conf="$1"

    if command -v python3 >/dev/null 2>&1; then
        python3 -c 'import shlex, sys
data = sys.argv[1]
for token in shlex.split(data):
    sys.stdout.buffer.write(token.encode("utf-8", "surrogateescape") + b"\0")' "$raw_conf"
        return $?
    fi

    if command -v python >/dev/null 2>&1; then
        python -c 'import shlex, sys
data = sys.argv[1]
for token in shlex.split(data):
    sys.stdout.buffer.write(token.encode("utf-8", "surrogateescape") + b"\0")' "$raw_conf"
        return $?
    fi

    return 127
}

parse_shell_words() {
    local raw_conf="${1:-}"
    local token=""

    PARSED_SHELL_WORDS=()
    [ -n "$raw_conf" ] || return 0

    if python_tokenizer "$raw_conf" >/dev/null 2>&1; then
        while IFS= read -r -d '' token; do
            PARSED_SHELL_WORDS+=("$token")
        done < <(python_tokenizer "$raw_conf")
        return 0
    fi

    logger "Warning: python is not available; falling back to bash parsing for SPARK_CONF."
    set -f
    eval "PARSED_SHELL_WORDS=( ${raw_conf} )"
    set +f
}

date_days_ago() {
    local days="${1:-1}"

    if TZ="CST" date -d "${days} days ago" '+%Y-%m-%d' >/dev/null 2>&1; then
        TZ="CST" date -d "${days} days ago" '+%Y-%m-%d'
        return 0
    fi

    TZ="CST" date -v-"${days}"d '+%Y-%m-%d'
}

date_today() {
    TZ="CST" date '+%Y-%m-%d'
}

cust_exit() {
    local exit_code="${1:-0}"

    krb_destroy >/dev/null 2>&1 || true
    exit "$exit_code"
}

parse_args() {
    additional_args=()

    while [ "$#" -gt 0 ]; do
        case "$1" in
            -e|--environment)
                shift
                if [ -z "${1:-}" ]; then
                    usage
                    cust_exit 1
                fi
                env="$1"
                ;;
            -c|--config)
                shift
                if [ -z "${1:-}" ]; then
                    usage
                    cust_exit 1
                fi
                wrapperConf="$1"
                ;;
            --)
                shift
                while [ "$#" -gt 0 ]; do
                    additional_args+=("$1")
                    shift
                done
                break
                ;;
            *)
                additional_args+=("$1")
                ;;
        esac
        shift
    done

    ENV=$(printf '%s' "$env" | tr '[:upper:]' '[:lower:]')

    if [ -z "$ENV" ] || [ -z "$wrapperConf" ]; then
        usage
        cust_exit 1
    fi

    logger "Arguments: ENV=\"$ENV\", Configfile=\"$wrapperConf\""
}

check_std_config_file() {
    if [ -z "${1:-}" ]; then
        logger "Error: Standard config file path is empty."
        cust_exit 1
    fi

    if [ ! -f "$1" ]; then
        logger "Error: Standard config file $1 does not exist."
        cust_exit 1
    fi
}

set_security_variables() {
    KEYSTORE_PWD="${KEYSTORE_PWD:-${TRUSTSTORE_PWD:-}}"
    TRUSTSTORE_PWD="${TRUSTSTORE_PWD:-${KEYSTORE_PWD:-}}"

    if [ -z "${CERT_PATH:-}" ] || [ -z "${KEYSTORE_FILE:-}" ] || [ -z "${TRUSTSTORE_FILE:-}" ] || [ -z "${KEYSTORE_PWD:-}" ] || [ -z "${TRUSTSTORE_PWD:-}" ]; then
        logger "Error: One or more security variables (CERT_PATH, KEYSTORE_FILE, TRUSTSTORE_FILE, KEYSTORE_PWD, TRUSTSTORE_PWD) are not set."
        cust_exit 1
    fi

    KEYSTORE="${CERT_PATH}/${KEYSTORE_FILE}"
    TRUSTSTORE="${CERT_PATH}/${TRUSTSTORE_FILE}"

    KEYTAB_PATH="${KEYTAB_PATH:-/opt/Cloudera/keytabs}"
    HOSTNAME_S="${HOSTNAME_S:-$(whoami).$(hostname -s).keytab}"
    KEYTAB="${KEYTAB:-${KEYTAB_PATH}/${HOSTNAME_S}}"
    PRINCIPAL="${PRINCIPAL:-$(whoami)/$(hostname -f)${ENV_PRINCIPAL:-}}"

    SPARK_FILE_LIST=$(join_by_comma "$KEYSTORE" "$TRUSTSTORE" "${CUSTOM_SPARK_FILE_ITEMS[@]}")
}

set_jar_files() {
    local framework_name=""
    local framework_version=""
    local dependency_jars_path=""
    local log4j_path=""
    local jar_path=""
    local streaming_framework_jar=""
    local spark_jar_list=()

    framework_name="${FRAMEWORK_NAME:-streaming_framework}"
    framework_version="${FRAMEWORK_VERSION:-2.0.0}"
    dependency_jars_path="${DEPENDENCY_JARS_PATH:-/deploy/app/169912_Foundation/Shared_Libraries/${framework_name}}"
    log4j_path="${LOG4J_PATH:-/deploy/app/169912_Foundation/Shared_Libraries/${framework_name}}"
    jar_path="${MAIN_JAR_PATH:-/deploy/app/169912_Foundation/Shared_Libraries/${framework_name}/${framework_version}/jars}"
    streaming_framework_jar="${STREAMING_FRAMEWORK_JAR_NAME:-real-time-dstream-2.12_2.0.0.jar}"

    MAIN_JAR="${jar_path}/${streaming_framework_jar}"
    spark_jar_list=(
        "${dependency_jars_path}/ojdbc6.jar"
        "${dependency_jars_path}/spark-sas7bdat-3.0.0-s_2.12.jar"
    )

    if [ -n "${CUSTOM_JARS:-}" ]; then
        spark_jar_list+=("${CUSTOM_JARS}")
    fi

    SPARK_JAR_LIST=$(join_by_comma "${spark_jar_list[@]}")

    LOG4J_FILE_DRIVER="${LOG4J_FILE_DRIVER:-log4j-driver.properties}"
    LOG4J_FILE_EXECUTOR="${LOG4J_FILE_EXECUTOR:-log4j-executor.properties}"
    CUSTOM_SPARK_FILE_ITEMS=()

    if [ -n "${CUSTOM_FILES:-}" ]; then
        CUSTOM_SPARK_FILE_ITEMS+=("${log4j_path}/${LOG4J_FILE_DRIVER}")
        CUSTOM_SPARK_FILE_ITEMS+=("${log4j_path}/${LOG4J_FILE_EXECUTOR}")
        CUSTOM_SPARK_FILE_ITEMS+=("${CUSTOM_FILES}")
    fi

    if [ -n "${FILES_TO_SUBMIT:-}" ]; then
        CUSTOM_SPARK_FILE_ITEMS+=("${FILES_TO_SUBMIT}")
    fi
}

check_pipeline_id_file() {
    if [ -z "${AUDIT_PIPELINE_ID_FILE_PATH:-}" ]; then
        logger "Pipeline Id file location not provided"
        audit_pipeline_id="${audit_pipeline_id:-}"
        return 0
    fi

    logger "Pipeline Id file location provided"

    if [ ! -e "${AUDIT_PIPELINE_ID_FILE_PATH}" ]; then
        local err_msg="Pipeline Id file not available in given path ${AUDIT_PIPELINE_ID_FILE_PATH}"
        logger "$err_msg"
        spark_audit_call "$err_msg"
        cust_exit 1
    fi

    # shellcheck disable=SC1090
    . "${AUDIT_PIPELINE_ID_FILE_PATH}"
    audit_pipeline_id="${audit_pipeline_id:-}"
    logger "audit_pipeline_id: ${audit_pipeline_id}"
}

set_spark_conf() {
    SPARK_APP_NAME="${SPARK_APP_NAME:-Streaming_Fwk_Job}"
    SPARK_CONF_OPTS=()

    if declare -p SPARK_CONF_ARRAY >/dev/null 2>&1; then
        SPARK_CONF_OPTS+=("${SPARK_CONF_ARRAY[@]}")
    fi

    if declare -p STATIC_SPARK_CONF_ARRAY >/dev/null 2>&1; then
        SPARK_CONF_OPTS+=("${STATIC_SPARK_CONF_ARRAY[@]}")
    fi

    if [ -n "${SPARK_CONF:-}" ]; then
        parse_shell_words "$SPARK_CONF"
        SPARK_CONF_OPTS+=("${PARSED_SHELL_WORDS[@]}")
    fi

    SPARK_CONF_OPTS+=(
        --conf "spark.yarn.appMasterEnv.SSL_TRUSTSTORE_LOCATION=${TRUSTSTORE_FILE}"
        --conf "spark.yarn.appMasterEnv.SSL_TRUSTSTORE_PASSWORD=${TRUSTSTORE_PWD}"
        --conf "spark.yarn.appMasterEnv.SSL_KEYSTORE_LOCATION=${KEYSTORE_FILE}"
        --conf "spark.yarn.appMasterEnv.SSL_KEYSTORE_PASSWORD=${KEYSTORE_PWD}"
        --conf "spark.yarn.appMasterEnv.keytab=${KEYTAB}"
        --conf "spark.yarn.appMasterEnv.principal=${PRINCIPAL}"
        --conf "spark.yarn.appMasterEnv.logUUID=${uuid}"
        --conf "spark.yarn.appMasterEnv.env=${ENV}"
        --conf "spark.yarn.appMasterEnv.fid=${FID}"
        --conf "spark.yarn.appMasterEnv.audit_pipeline_id=${audit_pipeline_id}"
        --conf "spark.yarn.appMasterEnv.audit_integration=${AUDIT_INTEGRATION:-}"
    )
}

submit_spark_job() {
    local CUSTOM_READ_FROM_DATE=""
    local CUSTOM_READ_TO_DATE=""
    local submit_cmd=()

    CUSTOM_READ_FROM_DATE="$(date_days_ago 1)"
    CUSTOM_READ_TO_DATE="$(date_today)"
    export SPARK_HOME="${SPARK_HOME:-/opt/cloudera/parcels/SPARK3/lib/spark3}"

    submit_cmd=(
        "$SPARK_SUBMIT_BIN"
        --master yarn
        --deploy-mode cluster
        --conf hive.exec.dynamic.partition.mode=nonstrict
        --conf hive.exec.dynamic.partition=true
        --conf spark.hadoop.hive.exec.dynamic.partition.mode=nonstrict
        --conf spark.hadoop.hive.exec.dynamic.partition=true
    )

    if [ -n "$SPARK_JAR_LIST" ]; then
        submit_cmd+=(--jars "$SPARK_JAR_LIST")
    fi

    if [ -n "$SPARK_FILE_LIST" ]; then
        submit_cmd+=(--files "$SPARK_FILE_LIST")
    fi

    submit_cmd+=("${SPARK_CONF_OPTS[@]}")
    submit_cmd+=(
        "$MAIN_JAR"
        "$TRUSTSTORE_PWD"
        "$KEYSTORE_PWD"
        "$CUSTOM_READ_TO_DATE"
        "$CUSTOM_READ_FROM_DATE"
    )
    submit_cmd+=("${additional_args[@]}")

    "${submit_cmd[@]}"
}

main() {
    if [ ! -f "$LOGGER_UTILS_PATH" ]; then
        logger "Warning: logger utils not found at ${LOGGER_UTILS_PATH}. Using built-in logger."
    fi

    if [ ! -f "$KRB_UTILS_PATH" ]; then
        logger "Warning: kerberos utils not found at ${KRB_UTILS_PATH}. Using no-op kerberos helpers."
    fi

    logger "1. Initiating Kerberos Token"
    krb_init

    logger "2. Mandatory Arguments Check and Validations"
    parse_args "$@"

    logger "3. Source configuration file"
    if [ ! -f "$wrapperConf" ]; then
        logger "Error: Wrapper config file ${wrapperConf} does not exist."
        cust_exit 1
    fi
    # shellcheck disable=SC1090
    . "$wrapperConf"

    logger "4. Check standard config file"
    check_std_config_file "${CFG_PATH:-}"

    logger "5. Set jar/files"
    set_jar_files

    logger "6. Setting security variables"
    set_security_variables

    logger "7. Check pipeline id file"
    check_pipeline_id_file

    logger "8. set spark configuration"
    set_spark_conf

    logger "9. Submitting Spark job"
    submit_spark_job

    if [ "$?" -ne 0 ]; then
        logger "spark-submit failed"
        cust_exit 1
    fi

    logger "spark-submit successful"
    cust_exit 0
}

if [ "${BASH_SOURCE[0]}" = "$0" ]; then
    main "$@"
fi
