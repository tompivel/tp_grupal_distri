package model

import (
	"time"
)

type ParquetArticle struct {
	Name               string                    `parquet:"name"`
	Identifier         int64                     `parquet:"identifier"`
	URL                string                    `parquet:"url"`
	DateCreated        *time.Time                `parquet:"date_created"`
	DateModified       *time.Time                `parquet:"date_modified"`
	IsPartOf           *parquetProject           `parquet:"is_part_of"`
	InLanguage         *parquetLanguage          `parquet:"in_language"`
	MainEntity         *parquetMainEntity        `parquet:"main_entity"`
	AdditionalEntities []parquetAdditionalEntity `parquet:"additional_entities"`
	Version            *parquetVersion           `parquet:"version"`
	Description        string                    `parquet:"description"`
	Abstract           string                    `parquet:"abstract"`
	Image              *parquetImage             `parquet:"image"`
	License            []parquetLicense          `parquet:"license"`
	Infoboxes          string                    `parquet:"infoboxes"`
	Sections           string                    `parquet:"sections"`
	Tables             string                    `parquet:"tables"`
	References         []parquetReference        `parquet:"references"`
}

type parquetProject struct {
	Identifier string `parquet:"identifier"`
	URL        string `parquet:"url"`
}

type parquetLanguage struct {
	Identifier string `parquet:"identifier"`
}

type parquetMainEntity struct {
	Identifier string `parquet:"identifier"`
	URL        string `parquet:"url"`
}

type parquetAdditionalEntity struct {
	Identifier string   `parquet:"identifier"`
	URL        string   `parquet:"url"`
	Aspects    []string `parquet:"aspects"`
}

type parquetVersion struct {
	Comment            string   `parquet:"comment"`
	Editor             string   `parquet:"editor"`
	Identifier         int64    `parquet:"identifier"`
	IsBreakingNews     *bool    `parquet:"is_breaking_news"`
	IsFlaggedStable    *bool    `parquet:"is_flagged_stable"`
	IsMinorEdit        *bool    `parquet:"is_minor_edit"`
	MaintenanceTags    string   `parquet:"maintenance_tags"`
	Noindex            bool     `parquet:"noindex"`
	NumberOfCharacters int64    `parquet:"number_of_characters"`
	Scores             string   `parquet:"scores"`
	Size               string   `parquet:"size"`
	Tags               []string `parquet:"tags"`
}

type parquetImage struct {
	ContentURL string `parquet:"content_url"`
	Height     int64  `parquet:"height"`
	Width      int64  `parquet:"width"`
}

type parquetLicense struct {
	Identifier string `parquet:"identifier"`
	Name       string `parquet:"name"`
	URL        string `parquet:"url"`
}

type parquetReference struct {
	Identifier string `parquet:"identifier"`
	Metadata   string `parquet:"metadata"`
	Source     string `parquet:"source"`
	Text       string `parquet:"text"`
	Type       string `parquet:"type"`
}
