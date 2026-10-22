package main

import (
	"bytes"
	"context"
	"crypto/sha256"
	"encoding/binary"
	"encoding/hex"
	"io"
	"testing"

	"github.com/rs/zerolog"
	"github.com/zricethezav/gitleaks/v8/detect"
	"github.com/zricethezav/gitleaks/v8/logging"
)

func frame(inputs ...[]byte) []byte {
	var b bytes.Buffer
	b.WriteString("SCB1")
	binary.Write(&b, binary.BigEndian, uint32(len(inputs)))
	var size uint64
	for _, item := range inputs {
		size += uint64(len(item))
	}
	binary.Write(&b, binary.BigEndian, size)
	for i, item := range inputs {
		binary.Write(&b, binary.BigEndian, uint32(i))
		binary.Write(&b, binary.BigEndian, uint32(len(item)))
		b.Write(item)
	}
	return b.Bytes()
}

func detectorForTest(t *testing.T) *detect.Detector {
	t.Helper()
	logging.Logger = zerolog.New(io.Discard)
	d, err := detect.NewDetectorDefaultConfig()
	if err != nil {
		t.Fatal("detector initialization failed")
	}
	d.IgnoreGitleaksAllow, d.Redact = true, 100
	return d
}

func TestBatchCompletionAndIsolation(t *testing.T) {
	d := detectorForTest(t)
	key := append([]byte("-----BEGIN "+"PRIVATE KEY-----\n"), bytes.Repeat([]byte("!invalid!"), 10)...)
	key = append(key, []byte("\n-----END "+"PRIVATE KEY-----\n")...)
	nearBoundary := append(bytes.Repeat([]byte("a"), 24950), '\n')
	nearBoundary = append(nearBoundary, key...)
	for _, inputs := range [][][]byte{{}, {nil, []byte("ordinary")}, {key, []byte("ordinary"), key}, {nearBoundary, []byte("ordinary"), key}} {
		r, err := scanBatch(context.Background(), bytes.NewReader(frame(inputs...)), d)
		if err != nil || !r.Complete || r.Processed != uint32(len(inputs)) {
			t.Fatal("missing completion")
		}
		if len(inputs) == 3 && (len(r.Findings) != 2 || r.Findings[0].Input != 0 || r.Findings[1].Input != 2) {
			t.Fatal("findings crossed inputs or disappeared")
		}
	}
	// Two individually harmless halves must not become a token by concatenation.
	digest := sha256.Sum256([]byte("inert regression fixture not an issued credential"))
	suffix := []byte(hex.EncodeToString(digest[:])[:36])
	ids, err := scanInput(context.Background(), d, append([]byte("ghp_"), suffix...))
	if err != nil || len(ids) == 0 {
		t.Fatal("isolation negative control is not detectable")
	}
	r, err := scanBatch(context.Background(), bytes.NewReader(frame([]byte("ghp_"), suffix)), d)
	if err != nil || len(r.Findings) != 0 {
		t.Fatal("input boundary changed detection")
	}
}

func TestMalformedOrIncompleteInput(t *testing.T) {
	d := detectorForTest(t)
	good := frame([]byte("ordinary"))
	wrongSequence := append([]byte(nil), good...)
	wrongSequence[19] = 1
	wrongBytes := append([]byte(nil), good...)
	wrongBytes[15]++
	oversize := frame(nil)
	binary.BigEndian.PutUint32(oversize[20:24], maxInput+1)
	for _, raw := range [][]byte{nil, []byte("SCB2"), good[:15], good[:len(good)-1], append(good, 'x'), wrongSequence, wrongBytes, oversize, frame([]byte{0}), frame([]byte{0xff}), frame([]byte("version https://git-lfs.github.com/spec/v1"))} {
		if r, err := scanBatch(context.Background(), bytes.NewReader(raw), d); err == nil || r.Complete {
			t.Fatal("invalid input passed")
		}
	}
	ctx, cancel := context.WithCancel(context.Background())
	cancel()
	if _, err := scanBatch(ctx, bytes.NewReader(good), d); err == nil {
		t.Fatal("cancelled scan passed")
	}
}

type brokenReader struct{}

func TestLFSPointerHeaderNotSubstring(t *testing.T) {
	for _, version := range []string{"https://git-lfs.github.com/spec/v1", "https://hawser.github.com/spec/v1", "http://git-media.io/v/2"} {
		header := "version " + version
		for _, data := range []string{header, header + "\noid invalid\nsize 1\n", "\u00a0 \n\t" + header + " \r\n", "```text\n" + header + "\n```"} {
			if validText([]byte(data)) {
				t.Fatal("pointer-like metadata accepted")
			}
		}
		if !validText([]byte("header = \"" + header + "\"\n")) {
			t.Fatal("source string rejected as a pointer")
		}
	}
}

func (brokenReader) Read([]byte) (int, error) { return 0, io.ErrUnexpectedEOF }

func TestReadFailureAndPolicyFailure(t *testing.T) {
	d := detectorForTest(t)
	if _, err := scanBatch(context.Background(), io.MultiReader(bytes.NewReader(frame()), brokenReader{}), d); err == nil {
		t.Fatal("read error passed")
	}
	var out bytes.Buffer
	if execute([]string{"--config", "main.go"}, bytes.NewReader(frame()), &out) != 2 || out.Len() != 0 {
		t.Fatal("unreviewed policy accepted")
	}
}
