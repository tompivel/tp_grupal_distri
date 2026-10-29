package model

import (
	"encoding/json"
	"fmt"
	"time"

	pb "github.com/7574-sistemas-distribuidos/tp-grupal-distri/gen/proto/common"
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

func (row ParquetArticle) ToProto() (*pb.Article, error) {
	article := pb.Article{
		Name:        row.Name,
		Identifier:  row.Identifier,
		Url:         row.URL,
		Description: row.Description, Abstract: row.Abstract,
	}

	if row.DateCreated != nil {
		article.DateCreated = row.DateCreated.Format(time.RFC3339Nano)
	}

	if row.DateModified != nil {
		article.DateModified = row.DateModified.Format(time.RFC3339Nano)
	}

	if row.IsPartOf != nil {
		article.IsPartOf = &pb.ArticleProject{
			Identifier: row.IsPartOf.Identifier,
			Name:       row.IsPartOf.URL,
		}
	}

	if row.InLanguage != nil {
		article.InLanguage = &pb.ArticleLanguage{
			Identifier: row.InLanguage.Identifier,
		}
	}

	if row.MainEntity != nil {
		article.MainEntity = &pb.ArticleMainEntity{
			Identifier: row.MainEntity.Identifier,
			Url:        row.MainEntity.URL,
		}
	}

	for _, entity := range row.AdditionalEntities {
		article.AdditionalEntities = append(
			article.AdditionalEntities,
			&pb.ArticleAdditionalEntity{
				Identifier: entity.Identifier,
				Url:        entity.URL,
				Aspects:    entity.Aspects,
			},
		)
	}

	if row.Version != nil {
		v := row.Version
		article.Version = &pb.ArticleVersion{
			Comment:            v.Comment,
			Editor:             v.Editor,
			Identifier:         v.Identifier,
			IsBreakingNews:     v.IsBreakingNews,
			IsFlaggedStabble:   v.IsFlaggedStable,
			IsMinorEdit:        v.IsMinorEdit,
			MaintenanceTags:    v.MaintenanceTags,
			Noindex:            v.Noindex,
			NumberOfCharacters: v.NumberOfCharacters,
			Scores:             v.Scores,
			Size:               v.Size,
			Tags:               v.Tags,
		}
	}

	if row.Image != nil {
		article.Image = &pb.ArticleImage{
			ContentUrl: row.Image.ContentURL,
			Height:     row.Image.Height,
			Width:      row.Image.Width,
		}
	}

	for _, item := range row.License {
		article.License = append(
			article.License,
			&pb.ArticleLicense{
				Identifier: item.Identifier,
				Name:       item.Name,
				Url:        item.URL,
			},
		)
	}

	infoboxes, err := decodeJSONArticleItems(row.Infoboxes)
	if err != nil {
		return &article, fmt.Errorf("parse infoboxes: %w", err)
	}
	article.Infoboxes = infoboxes

	sections, err := decodeJSONArticleItems(row.Sections)
	if err != nil {
		return &article, fmt.Errorf("parse sections: %w", err)
	}
	article.Sections = sections

	article.Tables, err = decodeJSONArticleTables(row.Tables)
	if err != nil {
		return &article, fmt.Errorf("parse tables: %w", err)
	}

	for _, ref := range row.References {
		article.References = append(
			article.References,
			&pb.ArticleReference{
				Identifier: ref.Identifier,
				Metadata:   ref.Metadata,
				Soruce:     ref.Source,
				Text:       ref.Text,
				Type:       ref.Type,
			},
		)
	}

	return &article, nil
}

func decodeJSONList[T any](raw string, dst *[]*T) error {
	if raw == "" || raw == "null" {
		return nil
	}
	return json.Unmarshal([]byte(raw), dst)
}

func decodeJSONArticleItems(raw string) ([]*pb.ArticleItem, error) {
	if raw == "" || raw == "null" {
		return nil, nil
	}

	var items []struct {
		Type     string          `json:"type"`
		Name     string          `json:"name"`
		HasParts json.RawMessage `json:"has_parts"`
	}
	if err := json.Unmarshal([]byte(raw), &items); err != nil {
		return nil, err
	}

	articles := make([]*pb.ArticleItem, 0, len(items))
	for _, item := range items {
		hasParts := ""
		if len(item.HasParts) > 0 && string(item.HasParts) != "null" {
			if err := json.Unmarshal(item.HasParts, &hasParts); err != nil {
				hasParts = string(item.HasParts)
			}
		}
		articles = append(articles, &pb.ArticleItem{
			Type:     item.Type,
			Name:     item.Name,
			HasParts: hasParts,
		})
	}
	return articles, nil
}

func decodeJSONArticleTables(raw string) ([]*pb.ArticleTable, error) {
	if raw == "" || raw == "null" {
		return nil, nil
	}

	var tables []struct {
		Identifier      string            `json:"identifier"`
		Headers         []json.RawMessage `json:"headers"`
		Rows            []json.RawMessage `json:"rows"`
		ConfidenceScore float32           `json:"confidence_score"`
	}
	if err := json.Unmarshal([]byte(raw), &tables); err != nil {
		return nil, err
	}

	articles := make([]*pb.ArticleTable, 0, len(tables))
	for _, table := range tables {
		articles = append(articles, &pb.ArticleTable{
			Identifier:      table.Identifier,
			Headers:         rawJSONStrings(table.Headers),
			Rows:            rawJSONStrings(table.Rows),
			ConfidenceScore: table.ConfidenceScore,
		})
	}
	return articles, nil
}

func rawJSONStrings(values []json.RawMessage) []string {
	result := make([]string, 0, len(values))
	for _, value := range values {
		var text string
		if err := json.Unmarshal(value, &text); err == nil {
			result = append(result, text)
		} else {
			result = append(result, string(value))
		}
	}
	return result
}
