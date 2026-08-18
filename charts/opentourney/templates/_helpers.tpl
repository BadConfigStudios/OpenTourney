{{- define "ot.fullname" -}}
{{ .Release.Name }}-{{ .Chart.Name | trunc 40 }}
{{- end -}}

{{- define "ot.labels" -}}
app.kubernetes.io/name: {{ .Chart.Name }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end -}}

{{/*
Composes a "scheme://domain[:port]" origin string, appending the port only
when it isn't the scheme's default (80 for http, 443 for https). Shared by
zitadel-deployment.yaml's ZITADEL_SYSTEM_API_AUDIENCE and
zitadel-login-configmap.yaml's AUDIENCE -- both must match core Zitadel's own
external URL exactly, since core's audience check does a literal string
compare (confirmed live: a mismatch here produces "audience is not valid").
Duplicating this logic once already caused a divergent bug (one copy used
Sprig's ternary(), which panics on the string-typed values --set-string
produces); a single template removes that failure mode.

Params (pass as a dict): "secure" (bool or "true"/"false" string -- accepts
either since --set-string always produces a string), "port" (int or numeric
string), "domain" (string -- a literal hostname or a shell-expanded
placeholder like "${ZITADEL_EXTERNALDOMAIN}", both work since this is a
plain string substitution).
*/}}
{{- define "ot.zitadelOrigin" -}}
{{- $secure := eq (toString .secure) "true" -}}
{{- $port := int .port -}}
{{- $isDefaultPort := or (and $secure (eq $port 443)) (and (not $secure) (eq $port 80)) -}}
http{{ if $secure }}s{{ end }}://{{ .domain }}{{ if not $isDefaultPort }}:{{ $port }}{{ end }}
{{- end -}}
