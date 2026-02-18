package mcp

import (
	"encoding/json"
	"net/http"
	"path/filepath"
	"strings"

	"github.com/archviz/backend-go/agent"
)

func NewHandlers(agent *agent.SimpleAgent) *Handlers {
	return &Handlers{agent: agent}
}

type Handlers struct {
	agent *agent.SimpleAgent
}

func (h *Handlers) Generate(w http.ResponseWriter, r *http.Request) {
	var payload map[string]interface{}
	_ = json.NewDecoder(r.Body).Decode(&payload)
	diagramType := "diagram"
	if v, ok := payload["diagram_type"].(string); ok && v != "" {
		diagramType = v
	}
	res, err := h.agent.Generate(diagramType)
	if err != nil {
		http.Error(w, err.Error(), http.StatusInternalServerError)
		return
	}
	w.Header().Set("Content-Type", "application/json")
	_ = json.NewEncoder(w).Encode(res)
}

func (h *Handlers) Feedback(w http.ResponseWriter, r *http.Request) {
	w.Header().Set("Content-Type", "application/json")
	_ = json.NewEncoder(w).Encode(map[string]string{"status": "ok"})
}

func (h *Handlers) IR(w http.ResponseWriter, r *http.Request) {
	id := strings.TrimPrefix(r.URL.Path, "/mcp/tool/ir/")
	if id == "" {
		http.Error(w, "missing id", http.StatusBadRequest)
		return
	}
	res := h.agent.GetIR(id)
	w.Header().Set("Content-Type", "application/json")
	_ = json.NewEncoder(w).Encode(res)
}

func (h *Handlers) ExportSVG(w http.ResponseWriter, r *http.Request) {
	id := strings.TrimPrefix(r.URL.Path, "/mcp/tool/export/svg/")
	if id == "" {
		http.Error(w, "missing id", http.StatusBadRequest)
		return
	}
	outputsDir := filepath.Join("outputs")
	matches, _ := filepath.Glob(filepath.Join(outputsDir, id+"_*.svg"))
	if len(matches) > 0 {
		http.ServeFile(w, r, matches[0])
		return
	}
	// fallback: generate inline
	svg := agent.GenerateSVG(id, "component")
	w.Header().Set("Content-Type", "image/svg+xml")
	_, _ = w.Write([]byte(svg))
}
