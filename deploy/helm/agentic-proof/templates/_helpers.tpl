{{- define "agentic-proof.fullname" -}}
{{- printf "%s-%s" .Release.Name "agentic-proof" | trunc 63 | trimSuffix "-" -}}
{{- end -}}
