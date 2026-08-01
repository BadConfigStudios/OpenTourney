{{- define "ot.fullname" -}}
{{ .Release.Name }}-{{ .Chart.Name | trunc 40 }}
{{- end -}}

{{- define "ot.labels" -}}
app.kubernetes.io/name: {{ .Chart.Name }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end -}}
