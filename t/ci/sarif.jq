walk(if type == "object" and (.uri | type) == "string"
     then .uri |= (sub("^file://"; "") | ltrimstr($root))
     elif type == "object" and has("startLine")
     then with_entries(select((.value | type) != "number" or .value >= 1))
     else . end)
| (.runs[].results[]?.codeFlows[]?.threadFlows[]?.locations)
  |= map(select(.location.physicalLocation != null))
