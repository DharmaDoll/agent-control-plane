// secret-checks-runner initializes the pinned detector once, never joins inputs,
// and reports completion only after every framed input and EOF were checked.
package main

import (
	"bytes"
	"context"
	"crypto/sha256"
	"encoding/binary"
	"encoding/hex"
	"encoding/json"
	"errors"
	"io"
	"os"
	"regexp"
	"runtime/debug"
	"sort"
	"time"
	"unicode/utf8"

	"github.com/rs/zerolog"
	"github.com/zricethezav/gitleaks/v8/detect"
	"github.com/zricethezav/gitleaks/v8/logging"
	"github.com/zricethezav/gitleaks/v8/sources"
)

const (
	maxInput  = 2 << 20
	maxTotal  = 32 << 20
	maxWire   = 64 << 20
	policySHA = "0407561445a76d93d1f7cdd5ee06c00dec57e997744759ba3ce70cf4fac49cc9"
)

var incomplete = errors.New("scan incomplete")

// Keep the host adapters and runner conservative about standalone metadata,
// without rejecting source code that quotes the version text.
var lfsHeader = regexp.MustCompile(`(?m)^[\t ]*version[\t ]+(https://git-lfs\.github\.com/spec/v1|https://hawser\.github\.com/spec/v1|http://git-media\.io/v/2)[\t ]*\r?$`)

type finding struct {
	Input uint32   `json:"input"`
	Rules []string `json:"rules"`
}

type report struct {
	Version   int       `json:"version"`
	Complete  bool      `json:"complete"`
	Processed uint32    `json:"processed"`
	Bytes     uint64    `json:"bytes"`
	Findings  []finding `json:"findings"`
}

func validText(data []byte) bool {
	if !utf8.Valid(data) || lfsHeader.Match(bytes.TrimSpace(data)) {
		return false
	}
	for _, b := range data {
		if b < 32 && b != '\t' && b != '\r' && b != '\n' {
			return false
		}
	}
	return true
}

func scanInput(ctx context.Context, detector *detect.Detector, data []byte) ([]string, error) {
	// Use upstream stdin fragmentation and the existing MIME-safe header. One
	// contiguous reader is important: MultiReader can return only the header on
	// its first read, introducing an artificial fragment boundary inside data.
	source := &sources.File{Content: bytes.NewReader(append([]byte("source002 text input\n"), data...))}
	rules := map[string]bool{}
	fragments := 0
	err := source.Fragments(ctx, func(fragment sources.Fragment, err error) error {
		if err != nil {
			return incomplete
		} // Unlike upstream DetectSource, do not swallow read errors.
		if ctx.Err() != nil {
			return incomplete
		}
		fragments++
		for _, f := range detector.DetectContext(ctx, detect.Fragment(fragment)) {
			rules[f.RuleID] = true
		}
		return ctx.Err()
	})
	if err != nil || fragments == 0 || ctx.Err() != nil {
		return nil, incomplete
	}
	ids := make([]string, 0, len(rules))
	for id := range rules {
		ids = append(ids, id)
	}
	sort.Strings(ids)
	return ids, nil
}

func scanBatch(ctx context.Context, input io.Reader, detector *detect.Detector) (report, error) {
	r := report{Version: 1, Findings: []finding{}}
	limited := &io.LimitedReader{R: input, N: maxWire + 1}
	magic := make([]byte, 4)
	if _, err := io.ReadFull(limited, magic); err != nil || string(magic) != "SCB1" {
		return r, incomplete
	}
	var count uint32
	var expected uint64
	if binary.Read(limited, binary.BigEndian, &count) != nil || binary.Read(limited, binary.BigEndian, &expected) != nil || expected > maxTotal || uint64(count)*8+16+expected > maxWire {
		return r, incomplete
	}
	for i := uint32(0); i < count; i++ {
		if ctx.Err() != nil {
			return r, incomplete
		}
		var sequence, size uint32
		if binary.Read(limited, binary.BigEndian, &sequence) != nil || binary.Read(limited, binary.BigEndian, &size) != nil || sequence != i || size > maxInput || r.Bytes+uint64(size) > expected {
			return r, incomplete
		}
		data := make([]byte, size)
		if _, err := io.ReadFull(limited, data); err != nil || !validText(data) {
			return r, incomplete
		}
		// Keep the former per-input 10-second limit as well as the batch deadline.
		itemContext, cancel := context.WithTimeout(ctx, 10*time.Second)
		ids, err := scanInput(itemContext, detector, data)
		cancel()
		if err != nil {
			return r, incomplete
		}
		if len(ids) > 0 {
			r.Findings = append(r.Findings, finding{Input: i, Rules: ids})
		}
		r.Bytes += uint64(size)
		r.Processed++
	}
	var tail [1]byte
	n, err := limited.Read(tail[:])
	if n != 0 || err != io.EOF || r.Bytes != expected || ctx.Err() != nil {
		return r, incomplete
	}
	r.Complete = true
	return r, nil
}

func execute(args []string, input io.Reader, output io.Writer) int {
	if len(args) != 2 || args[0] != "--config" {
		return 2
	}
	f, err := os.Open(args[1])
	if err != nil {
		return 2
	}
	policy, err := io.ReadAll(io.LimitReader(f, 4097))
	f.Close()
	digest := sha256.Sum256(policy)
	if err != nil || hex.EncodeToString(digest[:]) != policySHA {
		return 2
	}
	// The reviewed policy extends only upstream defaults. Never load ambient
	// config, ignores, baselines, environment settings or path-based exemptions.
	detector, err := detect.NewDetectorDefaultConfig()
	if err != nil {
		return 2
	}
	detector.IgnoreGitleaksAllow, detector.Redact = true, 100
	detector.MaxDecodeDepth, detector.MaxArchiveDepth = 0, 0
	ctx, cancel := context.WithTimeout(context.Background(), 120*time.Second)
	defer cancel()
	r, err := scanBatch(ctx, input, detector)
	if err != nil {
		return 2
	}
	if json.NewEncoder(output).Encode(r) != nil {
		return 2
	}
	if len(r.Findings) != 0 {
		return 10
	}
	return 0
}

func main() {
	// Suppress upstream logs even on malformed input; only our minimal report
	// may cross stdout. Do not enable Go diagnostics or write runtime dumps.
	logging.Logger = zerolog.New(io.Discard)
	debug.SetMemoryLimit(160 << 20)
	code := 2
	func() {
		defer func() {
			if recover() != nil {
				code = 2
			}
		}()
		code = execute(os.Args[1:], os.Stdin, os.Stdout)
	}()
	if code == 2 {
		_, _ = io.WriteString(os.Stderr, "ERROR batch scan incomplete\n")
	}
	os.Exit(code)
}
