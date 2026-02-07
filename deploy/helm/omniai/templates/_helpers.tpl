{{/*
Expand the name of the chart.
*/}}
{{- define "omniai.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Create a default fully qualified app name.
We truncate at 63 chars because some Kubernetes name fields are limited to this (by the DNS naming spec).
If release name contains chart name it will be used as a full name.
*/}}
{{- define "omniai.fullname" -}}
{{- if .Values.fullnameOverride }}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- $name := default .Chart.Name .Values.nameOverride }}
{{- if contains $name .Release.Name }}
{{- .Release.Name | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" }}
{{- end }}
{{- end }}
{{- end }}

{{/*
Create chart name and version as used by the chart label.
*/}}
{{- define "omniai.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Common labels
*/}}
{{- define "omniai.labels" -}}
helm.sh/chart: {{ include "omniai.chart" . }}
{{ include "omniai.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{/*
Selector labels
*/}}
{{- define "omniai.selectorLabels" -}}
app.kubernetes.io/name: {{ include "omniai.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{/*
Create the name of the service account to use
*/}}
{{- define "omniai.serviceAccountName" -}}
{{- if .Values.backend.serviceAccount.create }}
{{- default (include "omniai.fullname" .) .Values.backend.serviceAccount.name }}
{{- else }}
{{- default "default" .Values.backend.serviceAccount.name }}
{{- end }}
{{- end }}

{{/*
PostgreSQL connection string
*/}}
{{- define "omniai.databaseUrl" -}}
{{- if .Values.postgresql.enabled }}
{{- $postgresPassword := .Values.postgresql.auth.password | required "PostgreSQL password is required when postgresql.enabled=true" -}}
{{- printf "postgresql://%s:%s@%s-postgresql:5432/%s" .Values.postgresql.auth.username $postgresPassword (include "omniai.fullname" .) .Values.postgresql.auth.database }}
{{- else }}
{{- .Values.backend.env.DATABASE_URL }}
{{- end }}
{{- end }}

{{/*
Redis connection string
*/}}
{{- define "omniai.redisUrl" -}}
{{- if .Values.redis.enabled }}
{{- printf "redis://%s-redis-master:6379/0" (include "omniai.fullname" .) }}
{{- else }}
{{- .Values.backend.env.REDIS_URL }}
{{- end }}
{{- end }}
