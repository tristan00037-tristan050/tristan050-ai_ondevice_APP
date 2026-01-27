{{- define "onprem-gateway.name" -}}
onprem-gateway
{{- end -}}

{{- define "onprem-gateway.fullname" -}}
{{ include "onprem-gateway.name" . }}
{{- end -}}

