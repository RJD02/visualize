package main

import (
	"context"
	"encoding/json"
	"fmt"
	"log"
	"math/rand"
	"net/http"
	"net/http/httputil"
	"net/url"
	"os"
	"os/exec"
	"os/signal"
	"path/filepath"
	"strconv"
	"strings"
	"sync"
	"syscall"
	"time"

	"github.com/archviz/backend-go/agent"
	"github.com/archviz/backend-go/mcp"
)

// In-memory session store for standalone mode (minimal compatible subset)
type Session struct {
	ID      string                 `json:"session_id"`
	Title   string                 `json:"title"`
	Messages []map[string]any      `json:"messages"`
	Images  []map[string]any       `json:"images"`
	Diagrams []map[string]any      `json:"diagrams"`
	Plans   []map[string]any       `json:"plans"`
	SourceRepo *string             `json:"source_repo"`
	SourceCommit *string           `json:"source_commit"`
}

var (
	sessionsMu sync.Mutex
	sessions = map[string]*Session{}
	jobsMu sync.Mutex
	jobs = map[string]map[string]any{}
)

type config struct {
	Port            int
	UpstreamURL     string
	StartEmbeddedPy bool
	PyPort          int
	PyBin           string
	RootDir         string
}

func main() {
	cfg := loadConfig()
	mode := "standalone"
	if cfg.StartEmbeddedPy {
		mode = "proxy"
	}
	log.Printf("msg=starting_go_backend mode=%s port=%d upstream=%s start_embedded_python=%t", mode, cfg.Port, cfg.UpstreamURL, cfg.StartEmbeddedPy)

	var pyCmd *exec.Cmd
	var err error
	if cfg.StartEmbeddedPy {
		pyCmd, err = startEmbeddedPython(cfg)
		if err != nil {
			log.Fatalf("msg=failed_to_start_embedded_python err=%v", err)
		}
		defer stopProcess(pyCmd)

		if err := waitForHealth(cfg.UpstreamURL+"/health", 60*time.Second); err != nil {
			log.Fatalf("msg=upstream_not_ready err=%v", err)
		}

		target, err := url.Parse(cfg.UpstreamURL)
		if err != nil {
			log.Fatalf("msg=invalid_upstream_url err=%v", err)
		}

		proxy := httputil.NewSingleHostReverseProxy(target)
		proxy.ErrorHandler = func(w http.ResponseWriter, r *http.Request, e error) {
			log.Printf("msg=proxy_error method=%s path=%s err=%v", r.Method, r.URL.Path, e)
			w.Header().Set("Content-Type", "application/json")
			w.WriteHeader(http.StatusBadGateway)
			_, _ = w.Write([]byte(`{"error":"upstream unavailable"}`))
		}

		// If running in proxy mode, keep fallback proxy handler
		// Create mux so we can selectively handle some routes in Go (for migration)
		mux := http.NewServeMux()

		// initialize standalone agent and MCP handlers
		ag := agent.New(agent.AgentConfig{RootDir: cfg.RootDir})
		mcpHandlers := mcp.NewHandlers(ag)

		// Register MCP tool routes to be handled by Go directly (standalone)
		mux.HandleFunc("/mcp/tool/generate", mcpHandlers.Generate)
		mux.HandleFunc("/mcp/tool/feedback", mcpHandlers.Feedback)
		mux.HandleFunc("/mcp/tool/ir/", mcpHandlers.IR)
		mux.HandleFunc("/mcp/tool/export/svg/", mcpHandlers.ExportSVG)
		mux.HandleFunc("/mcp/tool/export/gif/", func(w http.ResponseWriter, r *http.Request) {
			http.Error(w, "gif export not implemented", http.StatusNotImplemented)
		})

		// session endpoints used by the UI
		mux.HandleFunc("/api/sessions", createSessionHandler)
		mux.HandleFunc("/api/sessions/", sessionDispatcher)

		// API endpoint used by the UI to fetch rendered SVGs
		mux.HandleFunc("/api/diagram/render", func(w http.ResponseWriter, r *http.Request) {
			q := r.URL.Query()
			imageId := q.Get("image_id")
			if imageId == "" {
				http.Error(w, "missing image_id", http.StatusBadRequest)
				return
			}
			outputsDir := filepath.Join(cfg.RootDir, "outputs")
			var found string
			files, _ := os.ReadDir(outputsDir)
			for _, f := range files {
				if strings.HasPrefix(f.Name(), imageId+"_") && strings.HasSuffix(f.Name(), ".svg") {
					found = filepath.Join(outputsDir, f.Name())
					break
				}
			}
			var svg string
			if found != "" {
				b, err := os.ReadFile(found)
				if err == nil {
					svg = string(b)
				}
			}
			if svg == "" {
				svg = agent.GenerateSVG(imageId, "component")
			}
			w.Header().Set("Content-Type", "application/json")
			_ = json.NewEncoder(w).Encode(map[string]string{"svg": svg})
		})

			// Health endpoint for standalone mode
			mux.HandleFunc("/health", func(w http.ResponseWriter, r *http.Request) {
				w.Header().Set("Content-Type", "application/json")
				_, _ = w.Write([]byte(`{"status":"ok"}`))
			})

		// Health endpoint used by tests/monitoring
		mux.HandleFunc("/health", func(w http.ResponseWriter, r *http.Request) {
			w.Header().Set("Content-Type", "application/json")
			_, _ = w.Write([]byte(`{"status":"ok"}`))
		})

		// Fallback: proxy everything else to upstream
		mux.HandleFunc("/", func(w http.ResponseWriter, r *http.Request) {
			proxy.ServeHTTP(w, r)
		})

		srv := &http.Server{
			Addr:              fmt.Sprintf(":%d", cfg.Port),
			Handler:           mux,
			ReadHeaderTimeout: 10 * time.Second,
		}

		go func() {
			log.Printf("msg=http_server_listening addr=%s", srv.Addr)
			if err := srv.ListenAndServe(); err != nil && err != http.ErrServerClosed {
				log.Fatalf("msg=server_crash err=%v", err)
			}
		}()

		sigCh := make(chan os.Signal, 1)
		signal.Notify(sigCh, syscall.SIGINT, syscall.SIGTERM)
		<-sigCh
		log.Printf("msg=shutdown_signal_received")

		ctx, cancel := context.WithTimeout(context.Background(), 15*time.Second)
		defer cancel()
		if err := srv.Shutdown(ctx); err != nil {
			log.Printf("msg=graceful_shutdown_failed err=%v", err)
		}

		return
	}

	// If not running embedded/python-proxy mode, start standalone Go server
	// Create mux and wire handlers that use the in-Go agent
	mux := http.NewServeMux()

	// initialize standalone agent and MCP handlers
	ag := agent.New(agent.AgentConfig{RootDir: cfg.RootDir})
	mcpHandlers := mcp.NewHandlers(ag)

	// Register MCP tool routes to be handled by Go directly (standalone)
	mux.HandleFunc("/mcp/tool/generate", mcpHandlers.Generate)
	mux.HandleFunc("/mcp/tool/feedback", mcpHandlers.Feedback)
	mux.HandleFunc("/mcp/tool/ir/", mcpHandlers.IR)
	mux.HandleFunc("/mcp/tool/export/svg/", mcpHandlers.ExportSVG)
	mux.HandleFunc("/mcp/tool/export/gif/", func(w http.ResponseWriter, r *http.Request) {
		http.Error(w, "gif export not implemented", http.StatusNotImplemented)
	})

	// session endpoints used by the UI
	mux.HandleFunc("/api/sessions", createSessionHandler)
	mux.HandleFunc("/api/sessions/", sessionDispatcher)

		// ingestion endpoints (global repo ingestion)
		mux.HandleFunc("/api/ingest", createIngestHandler)
		mux.HandleFunc("/api/ingest/", ingestStatusHandler)

	// API endpoint used by the UI to fetch rendered SVGs
	mux.HandleFunc("/api/diagram/render", func(w http.ResponseWriter, r *http.Request) {
		q := r.URL.Query()
		imageId := q.Get("image_id")
		if imageId == "" {
			http.Error(w, "missing image_id", http.StatusBadRequest)
			return
		}
		outputsDir := filepath.Join(cfg.RootDir, "outputs")
		var found string
		files, _ := os.ReadDir(outputsDir)
		for _, f := range files {
			if strings.HasPrefix(f.Name(), imageId+"_") && strings.HasSuffix(f.Name(), ".svg") {
				found = filepath.Join(outputsDir, f.Name())
				break
			}
		}
		var svg string
		if found != "" {
			b, err := os.ReadFile(found)
			if err == nil {
				svg = string(b)
			}
		}
		if svg == "" {
			svg = agent.GenerateSVG(imageId, "component")
		}
		w.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(w).Encode(map[string]string{"svg": svg})
	})

	// default fallback: return 404 for unknown routes (no upstream dependency)
	mux.HandleFunc("/", func(w http.ResponseWriter, r *http.Request) {
		http.NotFound(w, r)
	})

	srv := &http.Server{
		Addr:              fmt.Sprintf(":%d", cfg.Port),
		Handler:           mux,
		ReadHeaderTimeout: 10 * time.Second,
	}

	go func() {
		log.Printf("msg=http_server_listening addr=%s", srv.Addr)
		if err := srv.ListenAndServe(); err != nil && err != http.ErrServerClosed {
			log.Fatalf("msg=server_crash err=%v", err)
		}
	}()

	sigCh := make(chan os.Signal, 1)
	signal.Notify(sigCh, syscall.SIGINT, syscall.SIGTERM)
	<-sigCh
	log.Printf("msg=shutdown_signal_received")

	ctx, cancel := context.WithTimeout(context.Background(), 15*time.Second)
	defer cancel()
	if err := srv.Shutdown(ctx); err != nil {
		log.Printf("msg=graceful_shutdown_failed err=%v", err)
	}
}

func loadConfig() config {
	root := getenvDefault("PROJECT_ROOT", detectProjectRoot())
	port := parseIntEnv("PORT", 8000)
	pyPort := parseIntEnv("PY_BACKEND_INTERNAL_PORT", 18000)
	upstream := getenvDefault("GO_BACKEND_UPSTREAM", fmt.Sprintf("http://127.0.0.1:%d", pyPort))
	startEmbedded := getenvDefault("GO_START_EMBEDDED_PYTHON", "0") != "0"
	pyBin := getenvDefault("PYTHON_BIN", defaultPythonBin(root))

	return config{
		Port:            port,
		UpstreamURL:     upstream,
		StartEmbeddedPy: startEmbedded,
		PyPort:          pyPort,
		PyBin:           pyBin,
		RootDir:         root,
	}
}

func detectProjectRoot() string {
	cwd, _ := filepath.Abs(".")
	if filepath.Base(cwd) == "backend-go" {
		return filepath.Dir(cwd)
	}
	if _, err := os.Stat(filepath.Join(cwd, "backend-go", "go.mod")); err == nil {
		return cwd
	}
	return cwd
}

func defaultPythonBin(root string) string {
	venvBin := filepath.Join(root, ".venv", "bin", "python")
	if _, err := os.Stat(venvBin); err == nil {
		return venvBin
	}
	return "python3"
}

func startEmbeddedPython(cfg config) (*exec.Cmd, error) {
	cmd := exec.Command(cfg.PyBin, "-m", "src.app")
	cmd.Dir = cfg.RootDir
	cmd.Stdout = os.Stdout
	cmd.Stderr = os.Stderr
	cmd.Env = append(os.Environ(), fmt.Sprintf("PORT=%d", cfg.PyPort))
	if err := cmd.Start(); err != nil {
		return nil, err
	}
	log.Printf("msg=embedded_python_started pid=%d bin=%s port=%d", cmd.Process.Pid, cfg.PyBin, cfg.PyPort)
	return cmd, nil
}

func stopProcess(cmd *exec.Cmd) {
	if cmd == nil || cmd.Process == nil {
		return
	}
	_ = cmd.Process.Signal(syscall.SIGTERM)
	done := make(chan struct{})
	go func() {
		_, _ = cmd.Process.Wait()
		close(done)
	}()
	select {
	case <-done:
		return
	case <-time.After(8 * time.Second):
		_ = cmd.Process.Kill()
	}
}

func waitForHealth(url string, timeout time.Duration) error {
	deadline := time.Now().Add(timeout)
	for time.Now().Before(deadline) {
		resp, err := http.Get(url) // #nosec G107
		if err == nil {
			_ = resp.Body.Close()
			if resp.StatusCode == http.StatusOK {
				return nil
			}
		}
		time.Sleep(700 * time.Millisecond)
	}
	return fmt.Errorf("timeout waiting for %s", url)
}

func getenvDefault(key, fallback string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return fallback
}

func parseIntEnv(key string, fallback int) int {
	v := os.Getenv(key)
	if v == "" {
		return fallback
	}
	n, err := strconv.Atoi(v)
	if err != nil {
		return fallback
	}
	return n
}

// -----------------------------
// Minimal in-Go diagram agent
// -----------------------------

func generateHandler(cfg config) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		var payload map[string]interface{}
		_ = json.NewDecoder(r.Body).Decode(&payload)
		imageId := generateID()
		imageVersion := 1
		diagramType := "diagram"
		if v, ok := payload["diagram_type"].(string); ok && v != "" {
			diagramType = v
		}

		svg := generateSVGForImage(imageId, diagramType)
		outputsDir := filepath.Join(cfg.RootDir, "outputs")
		_ = os.MkdirAll(outputsDir, 0o755)
		fileName := fmt.Sprintf("%s_%s_%d.svg", imageId, diagramType, imageVersion)
		filePath := filepath.Join(outputsDir, fileName)
		_ = os.WriteFile(filePath, []byte(svg), 0o644)

		resp := map[string]interface{}{
			"image_id":      imageId,
			"image_version": imageVersion,
			"file_path":     fmt.Sprintf("/outputs/%s", fileName),
			"svg":           svg,
		}
		w.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(w).Encode(resp)
	}
}

func feedbackHandler(cfg config) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		// accept feedback, respond with simple ack
		w.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(w).Encode(map[string]any{"status": "ok"})
	}
}

func irHandler(cfg config) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		// return a minimal IR representation for requested id
		id := strings.TrimPrefix(r.URL.Path, "/mcp/tool/ir/")
		if id == "" {
			http.Error(w, "missing id", http.StatusBadRequest)
			return
		}
		ir := map[string]any{
			"id":  id,
			"ir":  fmt.Sprintf("digraph %s { nodeA -> nodeB }", id),
			"svg": generateSVGForImage(id, "component"),
		}
		w.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(w).Encode(ir)
	}
}

func exportSvgHandler(cfg config) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		// path like /mcp/tool/export/svg/{imageId}
		id := strings.TrimPrefix(r.URL.Path, "/mcp/tool/export/svg/")
		if id == "" {
			http.Error(w, "missing id", http.StatusBadRequest)
			return
		}
		svg := generateSVGForImage(id, "component")
		w.Header().Set("Content-Type", "image/svg+xml")
		_, _ = w.Write([]byte(svg))
	}
}

func exportGifHandler(cfg config) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		// For simplicity return a 501 until a proper GIF renderer is implemented
		http.Error(w, "gif export not implemented", http.StatusNotImplemented)
	}
}

func apiDiagramRenderHandler(cfg config) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		q := r.URL.Query()
		imageId := q.Get("image_id")
		if imageId == "" {
			http.Error(w, "missing image_id", http.StatusBadRequest)
			return
		}
		// try to read file from outputs
		outputsDir := filepath.Join(cfg.RootDir, "outputs")
		// pattern: <id>_*.svg
		var found string
		files, _ := os.ReadDir(outputsDir)
		for _, f := range files {
			if strings.HasPrefix(f.Name(), imageId+"_") && strings.HasSuffix(f.Name(), ".svg") {
				found = filepath.Join(outputsDir, f.Name())
				break
			}
		}
		var svg string
		if found != "" {
			b, err := os.ReadFile(found)
			if err == nil {
				svg = string(b)
			}
		}
		if svg == "" {
			svg = generateSVGForImage(imageId, "component")
		}
		w.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(w).Encode(map[string]string{"svg": svg})
	}
}

// --- minimal session handlers ---
func createSessionHandler(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
		return
	}
	id := generateID()
	s := &Session{
		ID: id,
		Title: fmt.Sprintf("Session %s", id),
		Messages: []map[string]any{},
		Images: []map[string]any{},
		Diagrams: []map[string]any{},
		Plans: []map[string]any{},
	}
	sessionsMu.Lock()
	sessions[id] = s
	sessionsMu.Unlock()
	w.Header().Set("Content-Type", "application/json")
	_ = json.NewEncoder(w).Encode(map[string]string{"session_id": id})
}

func sessionDispatcher(w http.ResponseWriter, r *http.Request) {
	// path: /api/sessions/{id} or /api/sessions/{id}/messages or /api/sessions/{id}/ingest
	p := strings.TrimPrefix(r.URL.Path, "/api/sessions/")
	if p == "" {
		http.NotFound(w, r)
		return
	}
	parts := strings.SplitN(p, "/", 2)
	id := parts[0]
	sub := ""
	if len(parts) == 2 {
		sub = parts[1]
	}

	sessionsMu.Lock()
	s, ok := sessions[id]
	sessionsMu.Unlock()
	if !ok {
		http.Error(w, "session not found", http.StatusNotFound)
		return
	}

	switch {
	case sub == "" && r.Method == http.MethodGet:
		// return session detail
		w.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(w).Encode(map[string]any{
			"session_id": s.ID,
			"title": s.Title,
			"messages": s.Messages,
			"images": s.Images,
			"diagrams": s.Diagrams,
			"plans": s.Plans,
			"source_repo": s.SourceRepo,
			"source_commit": s.SourceCommit,
		})
		return
	case sub == "messages" && r.Method == http.MethodPost:
		var payload map[string]any
		_ = json.NewDecoder(r.Body).Decode(&payload)
		msg := map[string]any{"id": generateID(), "content": payload["content"]}
		sessionsMu.Lock()
		s.Messages = append(s.Messages, msg)
		sessionsMu.Unlock()
		w.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(w).Encode(msg)
		return
	case sub == "ingest" && (r.Method == http.MethodPost || r.Method == http.MethodPut):
		// minimal stub: accept and return a job id
		jobId := generateID()
		w.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(w).Encode(map[string]any{"job_id": jobId, "status": "queued"})
		return
	default:
		http.Error(w, "not implemented", http.StatusNotFound)
		return
	}
}

// --- minimal ingest job handlers ---
func createIngestHandler(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
		return
	}
	var payload map[string]any
	_ = json.NewDecoder(r.Body).Decode(&payload)
	jobId := generateID()
	job := map[string]any{
		"job_id": jobId,
		"status": "queued",
		"result": nil,
		"error": nil,
	}
	jobsMu.Lock()
	jobs[jobId] = job
	jobsMu.Unlock()

	// simulate background ingestion: complete after short delay
	go func(jid string, p map[string]any) {
		time.Sleep(1500 * time.Millisecond)
		jobsMu.Lock()
		if j, ok := jobs[jid]; ok {
			j["status"] = "complete"
			j["result"] = map[string]any{"diagrams": []any{}}
			jobs[jid] = j
		}
		jobsMu.Unlock()

		// if session_id provided, add a placeholder image to session
		if sidRaw, ok := p["session_id"].(string); ok && sidRaw != "" {
			sessionsMu.Lock()
			if s, ok := sessions[sidRaw]; ok {
				img := map[string]any{"id": generateID(), "version": 1, "file_path": "", "title": "Ingested Diagram"}
				s.Images = append(s.Images, img)
				sessions[sidRaw] = s
			}
			sessionsMu.Unlock()
		}
	}(jobId, payload)

	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(http.StatusAccepted)
	_ = json.NewEncoder(w).Encode(job)
}

func ingestStatusHandler(w http.ResponseWriter, r *http.Request) {
	// GET /api/ingest/{jobId}
	if r.Method != http.MethodGet {
		http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
		return
	}
	id := strings.TrimPrefix(r.URL.Path, "/api/ingest/")
	if id == "" {
		http.Error(w, "missing id", http.StatusBadRequest)
		return
	}
	jobsMu.Lock()
	job, ok := jobs[id]
	jobsMu.Unlock()
	if !ok {
		http.Error(w, "job not found", http.StatusNotFound)
		return
	}
	w.Header().Set("Content-Type", "application/json")
	_ = json.NewEncoder(w).Encode(job)
}

func generateID() string {
	return fmt.Sprintf("gox%016x", uint64(time.Now().UnixNano())^uint64(rand.Int63()))
}

func generateSVGForImage(id, diagramType string) string {
	// deterministic simple SVG; real implementation would call LLM/IR/renderers
	return fmt.Sprintf(`<?xml version="1.0" encoding="UTF-8"?>
<svg width="300" height="140" viewBox="0 0 300 140" xmlns="http://www.w3.org/2000/svg">
  <rect x="10" y="20" width="120" height="60" fill="#4f46e5" stroke="#1e1b4b" stroke-width="2" />
  <rect x="170" y="20" width="120" height="60" fill="#14b8a6" stroke="#0f766e" stroke-width="2" />
  <text x="70" y="55" font-size="12" fill="#fff" text-anchor="middle">%s</text>
  <text x="230" y="55" font-size="12" fill="#fff" text-anchor="middle">%s</text>
</svg>`, strings.ToUpper(diagramType), id)
}
