package main

import (
	"os"

	"github.com/7574-sistemas-distribuidos/tp-grupal-distri/workers/bioFilter/bioFilter"
)

func main() {
	os.Exit(bioFilter.Run())
}
