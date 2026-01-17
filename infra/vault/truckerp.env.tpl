{{- with secret "secret/data/truckerp/platform" -}}
JWT_SECRET={{ .Data.data.JWT_SECRET }}
PLATFORM_DATABASE_URL={{ .Data.data.PLATFORM_DATABASE_URL }}
{{- end -}}
