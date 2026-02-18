package agent

import (
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"time"
)

type AgentConfig struct {
	RootDir string
}

// SimpleAgent provides basic diagram generation, IR and rendering.
type SimpleAgent struct {
	cfg AgentConfig
}

func New(cfg AgentConfig) *SimpleAgent {
	return &SimpleAgent{cfg: cfg}
}

func (a *SimpleAgent) SaveSVG(imageId, diagramType, svg string) (string, error) {
	outputsDir := filepath.Join(a.cfg.RootDir, "outputs")
	if err := os.MkdirAll(outputsDir, 0o755); err != nil {
		return "", err
	}
	fileName := fmt.Sprintf("%s_%s_1.svg", imageId, sanitize(diagramType))
	filePath := filepath.Join(outputsDir, fileName)
	if err := os.WriteFile(filePath, []byte(svg), 0o644); err != nil {
		return "", err
	}
	return filePath, nil
}

func (a *SimpleAgent) Generate(imageType string) (map[string]interface{}, error) {
	id := fmt.Sprintf("gox%016x", uint64(time.Now().UnixNano()))
	svg := GenerateSVG(id, imageType)
	path, err := a.SaveSVG(id, imageType, svg)
	if err != nil {
		return nil, err
	}
	return map[string]interface{}{
		"image_id":      id,
		"image_version": 1,
		"file_path":     strings.TrimPrefix(path, a.cfg.RootDir),
		"svg":           svg,
	}, nil
}

func (a *SimpleAgent) GetIR(id string) map[string]interface{} {
	return map[string]interface{}{
		"id": id,
		"ir": fmt.Sprintf("digraph %s { A -> B }", id),
	}
}

func GenerateSVG(id, diagramType string) string {
	return fmt.Sprintf(`<?xml version="1.0" encoding="UTF-8"?>
<svg width="300" height="140" viewBox="0 0 300 140" xmlns="http://www.w3.org/2000/svg">
  <rect x="10" y="20" width="120" height="60" fill="#4f46e5" stroke="#1e1b4b" stroke-width="2" />
  <rect x="170" y="20" width="120" height="60" fill="#14b8a6" stroke="#0f766e" stroke-width="2" />
  <text x="70" y="55" font-size="12" fill="#fff" text-anchor="middle">%s</text>
  <text x="230" y="55" font-size="12" fill="#fff" text-anchor="middle">%s</text>
</svg>`, strings.ToUpper(diagramType), id)
}

func sanitize(s string) string {
	return strings.ReplaceAll(strings.ToLower(s), " ", "_")
}
