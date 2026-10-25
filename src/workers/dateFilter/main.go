package main

import (
	"os"

	"github.com/7574-sistemas-distribuidos/tp-grupal-distri/workers/dateFilter/dateFilter"
)

func main() {
	os.Exit(dateFilter.Run())
}
