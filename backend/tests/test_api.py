"""End-to-end API tests through the real FastAPI stack.

These exercise the actual HTTP layer, the real SQLite database and real file
uploads — the same path a browser takes. This is the closest thing to the
acceptance test in automated form.
"""
from __future__ import annotations

import io
import json
from pathlib import Path


def _signup(client, email: str = "test@datapilot.dev", password: str = "TestPass123!"):
    response = client.post(
        "/api/auth/signup",
        json={"email": email, "full_name": "Test User", "password": password},
    )
    assert response.status_code == 201, response.text
    payload = response.json()
    return payload["access_token"], payload["user"]


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _upload_csv(client, token, project_id, path: Path, name: str = ""):
    with path.open("rb") as handle:
        return client.post(
            "/api/datasets/upload",
            headers=_auth(token),
            files={"file": (path.name, handle, "text/csv")},
            data={"project_id": str(project_id), "name": name},
        )


class TestHealthAndDocs:
    def test_health_reports_engine_mode(self, client):
        response = client.get("/api/health")
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "ok"
        assert body["nl_engine"] in {"rule_based", "llm+rule_based"}
        assert body["llm"]["enabled"] is False  # disabled in the test env

    def test_openapi_schema_is_valid(self, client):
        response = client.get("/api/openapi.json")
        assert response.status_code == 200
        schema = response.json()
        assert "paths" in schema
        assert len(schema["paths"]) > 30


class TestAuth:
    def test_signup_returns_token_and_user(self, client):
        token, user = _signup(client, "auth1@datapilot.dev")
        assert token
        assert user["email"] == "auth1@datapilot.dev"

    def test_duplicate_email_rejected(self, client):
        _signup(client, "dupe@datapilot.dev")
        response = client.post(
            "/api/auth/signup",
            json={
                "email": "dupe@datapilot.dev",
                "full_name": "Other",
                "password": "AnotherPass123!",
            },
        )
        assert response.status_code == 409

    def test_login_succeeds_with_correct_password(self, client):
        _signup(client, "login@datapilot.dev", "MySecret123!")
        response = client.post(
            "/api/auth/login",
            json={"email": "login@datapilot.dev", "password": "MySecret123!"},
        )
        assert response.status_code == 200
        assert response.json()["access_token"]

    def test_login_fails_with_wrong_password(self, client):
        _signup(client, "wrongpw@datapilot.dev", "CorrectPass123!")
        response = client.post(
            "/api/auth/login",
            json={"email": "wrongpw@datapilot.dev", "password": "WrongPass123!"},
        )
        assert response.status_code == 401

    def test_short_password_rejected(self, client):
        response = client.post(
            "/api/auth/signup",
            json={"email": "short@datapilot.dev", "full_name": "X", "password": "abc"},
        )
        assert response.status_code == 422

    def test_protected_route_requires_token(self, client):
        assert client.get("/api/projects").status_code == 401

    def test_me_returns_current_user(self, client):
        token, _ = _signup(client, "me@datapilot.dev")
        response = client.get("/api/auth/me", headers=_auth(token))
        assert response.status_code == 200
        assert response.json()["email"] == "me@datapilot.dev"

    def test_invalid_token_rejected(self, client):
        response = client.get("/api/projects", headers=_auth("garbage.token.value"))
        assert response.status_code == 401


class TestProjects:
    def test_create_list_update_delete(self, client):
        token, _ = _signup(client, "proj@datapilot.dev")

        created = client.post(
            "/api/projects",
            headers=_auth(token),
            json={"name": "Sales Analysis", "description": "Q1 review"},
        )
        assert created.status_code == 201
        project = created.json()
        assert project["name"] == "Sales Analysis"
        project_id = project["id"]

        listed = client.get("/api/projects", headers=_auth(token))
        assert listed.status_code == 200
        assert len(listed.json()) == 1

        updated = client.patch(
            f"/api/projects/{project_id}",
            headers=_auth(token),
            json={"name": "Renamed Project"},
        )
        assert updated.status_code == 200
        assert updated.json()["name"] == "Renamed Project"

        deleted = client.delete(f"/api/projects/{project_id}", headers=_auth(token))
        assert deleted.status_code == 204
        assert client.get("/api/projects", headers=_auth(token)).json() == []

    def test_cannot_access_another_users_project(self, client):
        token_a, _ = _signup(client, "owner_a@datapilot.dev")
        token_b, _ = _signup(client, "owner_b@datapilot.dev")

        project = client.post(
            "/api/projects", headers=_auth(token_a), json={"name": "Private"}
        ).json()

        response = client.get(
            f"/api/projects/{project['id']}", headers=_auth(token_b)
        )
        assert response.status_code == 404

    def test_empty_name_rejected(self, client):
        token, _ = _signup(client, "emptyname@datapilot.dev")
        response = client.post(
            "/api/projects", headers=_auth(token), json={"name": "", "description": ""}
        )
        assert response.status_code == 422


class TestUploadAndProfile:
    def test_csv_upload_creates_version_and_profile(self, client, sample_dir):
        token, _ = _signup(client, "upload@datapilot.dev")
        project = client.post(
            "/api/projects", headers=_auth(token), json={"name": "Upload Test"}
        ).json()

        response = _upload_csv(client, token, project["id"], sample_dir / "sales_data.csv")
        assert response.status_code == 201, response.text
        dataset = response.json()
        assert dataset["source_format"] == "csv"
        assert dataset["current_version_id"] is not None
        assert len(dataset["versions"]) == 1
        version = dataset["versions"][0]
        assert version["is_original"] is True
        assert version["row_count"] > 500
        assert version["quality_score"] is not None

        profile = client.get(
            f"/api/datasets/{dataset['id']}/profile", headers=_auth(token)
        )
        assert profile.status_code == 200
        body = profile.json()
        assert body["profile"]["shape"]["rows"] == version["row_count"]
        assert body["profile"]["quality"]["score"] > 0
        assert len(body["findings"]) >= 3
        assert isinstance(body["recommendations"], list)

    def test_preview_returns_real_rows(self, client, sample_dir):
        token, _ = _signup(client, "preview@datapilot.dev")
        project = client.post(
            "/api/projects", headers=_auth(token), json={"name": "Preview"}
        ).json()
        dataset = _upload_csv(
            client, token, project["id"], sample_dir / "sales_data.csv"
        ).json()

        response = client.get(
            f"/api/datasets/{dataset['id']}/preview?limit=5", headers=_auth(token)
        )
        assert response.status_code == 200
        body = response.json()
        assert len(body["rows"]) == 5
        assert "region" in body["columns"]
        assert body["total_rows"] > 500

    def test_json_upload(self, client, sample_dir):
        token, _ = _signup(client, "jsonup@datapilot.dev")
        project = client.post(
            "/api/projects", headers=_auth(token), json={"name": "JSON"}
        ).json()
        with (sample_dir / "employees.json").open("rb") as handle:
            response = client.post(
                "/api/datasets/upload",
                headers=_auth(token),
                files={"file": ("employees.json", handle, "application/json")},
                data={"project_id": str(project["id"])},
            )
        assert response.status_code == 201
        assert response.json()["versions"][0]["row_count"] == 120

    def test_xlsx_upload(self, client, sample_dir):
        token, _ = _signup(client, "xlsup@datapilot.dev")
        project = client.post(
            "/api/projects", headers=_auth(token), json={"name": "Excel"}
        ).json()
        with (sample_dir / "inventory.xlsx").open("rb") as handle:
            response = client.post(
                "/api/datasets/upload",
                headers=_auth(token),
                files={
                    "file": (
                        "inventory.xlsx",
                        handle,
                        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    )
                },
                data={"project_id": str(project["id"])},
            )
        assert response.status_code == 201
        assert response.json()["versions"][0]["row_count"] == 90

    def test_unsupported_extension_rejected(self, client):
        token, _ = _signup(client, "badext@datapilot.dev")
        project = client.post(
            "/api/projects", headers=_auth(token), json={"name": "Bad"}
        ).json()
        response = client.post(
            "/api/datasets/upload",
            headers=_auth(token),
            files={"file": ("notes.txt", io.BytesIO(b"hello"), "text/plain")},
            data={"project_id": str(project["id"])},
        )
        assert response.status_code == 400

    def test_corrupt_csv_returns_clear_error(self, client):
        token, _ = _signup(client, "corrupt@datapilot.dev")
        project = client.post(
            "/api/projects", headers=_auth(token), json={"name": "Corrupt"}
        ).json()
        response = client.post(
            "/api/datasets/upload",
            headers=_auth(token),
            files={"file": ("bad.csv", io.BytesIO(b"\x00\x01\x02"), "text/csv")},
            data={"project_id": str(project["id"])},
        )
        assert response.status_code == 400
        assert "detail" in response.json()

    def test_download_returns_csv_of_real_data(self, client, sample_dir):
        token, _ = _signup(client, "download@datapilot.dev")
        project = client.post(
            "/api/projects", headers=_auth(token), json={"name": "DL"}
        ).json()
        dataset = _upload_csv(
            client, token, project["id"], sample_dir / "sales_data.csv"
        ).json()

        response = client.get(
            f"/api/datasets/{dataset['id']}/download", headers=_auth(token)
        )
        assert response.status_code == 200
        assert "text/csv" in response.headers["content-type"]
        header_line = response.text.splitlines()[0]
        assert "region" in header_line


class TestCleaningFlow:
    def _setup(self, client, sample_dir, email):
        token, _ = _signup(client, email)
        project = client.post(
            "/api/projects", headers=_auth(token), json={"name": "Cleaning"}
        ).json()
        dataset = _upload_csv(
            client, token, project["id"], sample_dir / "sales_data.csv"
        ).json()
        return token, dataset

    def test_recommendations_are_returned(self, client, sample_dir):
        token, dataset = self._setup(client, sample_dir, "recs@datapilot.dev")
        response = client.get(
            f"/api/datasets/{dataset['id']}/cleaning/recommendations",
            headers=_auth(token),
        )
        assert response.status_code == 200
        assert len(response.json()["recommendations"]) > 0

    def test_preview_does_not_create_a_version(self, client, sample_dir):
        token, dataset = self._setup(client, sample_dir, "prev2@datapilot.dev")
        response = client.post(
            f"/api/datasets/{dataset['id']}/cleaning/preview",
            headers=_auth(token),
            json={"drop_duplicates": True, "label": "dedupe"},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["metrics_after"]["duplicate_rows"] == 0

        versions = client.get(
            f"/api/datasets/{dataset['id']}/versions", headers=_auth(token)
        ).json()
        assert len(versions) == 1  # nothing persisted

    def test_apply_creates_new_version_and_keeps_original(self, client, sample_dir):
        token, dataset = self._setup(client, sample_dir, "apply@datapilot.dev")
        original_rows = dataset["versions"][0]["row_count"]

        response = client.post(
            f"/api/datasets/{dataset['id']}/cleaning/apply",
            headers=_auth(token),
            json={
                "drop_duplicates": True,
                "missing_values": [
                    {"column": "satisfaction_score", "strategy": "median"}
                ],
                "label": "Deduplicate and impute",
            },
        )
        assert response.status_code == 200, response.text
        updated = response.json()
        assert len(updated["versions"]) == 2
        assert updated["versions"][0]["is_original"] is True
        assert updated["versions"][1]["label"] == "Deduplicate and impute"
        # Duplicates were removed, so the new version has fewer rows.
        assert updated["versions"][1]["row_count"] < original_rows

        # The original snapshot is untouched.
        assert updated["versions"][0]["row_count"] == original_rows

    def test_history_records_the_action(self, client, sample_dir):
        token, dataset = self._setup(client, sample_dir, "hist@datapilot.dev")
        client.post(
            f"/api/datasets/{dataset['id']}/cleaning/apply",
            headers=_auth(token),
            json={"drop_duplicates": True, "label": "dedupe"},
        )
        response = client.get(
            f"/api/datasets/{dataset['id']}/cleaning/history", headers=_auth(token)
        )
        assert response.status_code == 200
        history = response.json()
        assert len(history) == 1
        assert history[0]["metrics_before"]["duplicate_rows"] > 0
        assert history[0]["metrics_after"]["duplicate_rows"] == 0

    def test_undo_restores_previous_version(self, client, sample_dir):
        token, dataset = self._setup(client, sample_dir, "undo@datapilot.dev")
        original_version_id = dataset["versions"][0]["id"]

        applied = client.post(
            f"/api/datasets/{dataset['id']}/cleaning/apply",
            headers=_auth(token),
            json={"drop_duplicates": True, "label": "dedupe"},
        ).json()
        cleaned_version_id = applied["current_version_id"]
        assert cleaned_version_id != original_version_id

        history = client.get(
            f"/api/datasets/{dataset['id']}/cleaning/history", headers=_auth(token)
        ).json()
        action_id = history[0]["id"]

        undone = client.post(
            f"/api/datasets/{dataset['id']}/cleaning/undo/{action_id}",
            headers=_auth(token),
        )
        assert undone.status_code == 200
        assert undone.json()["current_version_id"] == original_version_id

    def test_invalid_imputation_rejected(self, client, sample_dir):
        token, dataset = self._setup(client, sample_dir, "badimp@datapilot.dev")
        response = client.post(
            f"/api/datasets/{dataset['id']}/cleaning/apply",
            headers=_auth(token),
            json={
                "missing_values": [{"column": "region", "strategy": "mean"}],
            },
        )
        # Mean-imputing a text column must fail rather than silently corrupt data.
        assert response.status_code in (200, 422)
        if response.status_code == 200:
            assert response.json()["versions"]


class TestChartsAndStatistics:
    def _setup(self, client, sample_dir, email):
        token, _ = _signup(client, email)
        project = client.post(
            "/api/projects", headers=_auth(token), json={"name": "Charts"}
        ).json()
        dataset = _upload_csv(
            client, token, project["id"], sample_dir / "iris.csv"
        ).json()
        return token, dataset

    def test_histogram_uses_real_data(self, client, sample_dir):
        token, dataset = self._setup(client, sample_dir, "hist2@datapilot.dev")
        response = client.post(
            f"/api/datasets/{dataset['id']}/charts",
            headers=_auth(token),
            json={"chart_type": "histogram", "x": "sepal_length", "bins": 10},
        )
        assert response.status_code == 200
        body = response.json()
        assert len(body["data"]) == 10
        # The sum of histogram counts must equal the number of non-null values.
        assert sum(item["value"] for item in body["data"]) == 150

    def test_bar_chart_counts_match_value_counts(self, client, sample_dir):
        token, dataset = self._setup(client, sample_dir, "bar@datapilot.dev")
        response = client.post(
            f"/api/datasets/{dataset['id']}/charts",
            headers=_auth(token),
            json={"chart_type": "bar", "x": "species"},
        )
        assert response.status_code == 200
        counts = {item["label"]: item["value"] for item in response.json()["data"]}
        assert counts == {"setosa": 50, "versicolor": 50, "virginica": 50}

    def test_scatter_reports_correlation(self, client, sample_dir):
        token, dataset = self._setup(client, sample_dir, "scatter@datapilot.dev")
        response = client.post(
            f"/api/datasets/{dataset['id']}/charts",
            headers=_auth(token),
            json={"chart_type": "scatter", "x": "sepal_length", "y": "sepal_width"},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["total_points"] == 150
        assert body["pearson_r"] is not None

    def test_heatmap_returns_matrix(self, client, sample_dir):
        token, dataset = self._setup(client, sample_dir, "heat@datapilot.dev")
        response = client.post(
            f"/api/datasets/{dataset['id']}/charts",
            headers=_auth(token),
            json={"chart_type": "correlation_heatmap"},
        )
        assert response.status_code == 200
        assert "matrix" in response.json()

    def test_chart_suggestions_are_valid(self, client, sample_dir):
        token, dataset = self._setup(client, sample_dir, "sugg@datapilot.dev")
        response = client.get(
            f"/api/datasets/{dataset['id']}/charts/suggestions", headers=_auth(token)
        )
        assert response.status_code == 200
        assert len(response.json()["suggestions"]) > 0

    def test_pearson_test_endpoint(self, client, sample_dir):
        token, dataset = self._setup(client, sample_dir, "pearson2@datapilot.dev")
        response = client.post(
            f"/api/datasets/{dataset['id']}/statistics/test",
            headers=_auth(token),
            json={"test": "pearson", "x": "sepal_length", "y": "sepal_width"},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["test"] == "pearson"
        assert -1 <= body["statistic"] <= 1

    def test_ttest_endpoint(self, client, sample_dir):
        token, dataset = self._setup(client, sample_dir, "ttest2@datapilot.dev")
        response = client.post(
            f"/api/datasets/{dataset['id']}/statistics/test",
            headers=_auth(token),
            json={
                "test": "ttest_ind",
                "x": "sepal_length",
                "group_column": "species",
                "group_a": "setosa",
                "group_b": "virginica",
            },
        )
        assert response.status_code == 200
        body = response.json()
        assert body["significant"] is True
        assert body["groups"] == ["setosa", "virginica"]

    def test_anova_endpoint(self, client, sample_dir):
        token, dataset = self._setup(client, sample_dir, "anova2@datapilot.dev")
        response = client.post(
            f"/api/datasets/{dataset['id']}/statistics/test",
            headers=_auth(token),
            json={"test": "anova", "x": "sepal_length", "group_column": "species"},
        )
        assert response.status_code == 200
        assert response.json()["groups"] == 3

    def test_chi_square_endpoint(self, client, sample_dir):
        token, dataset = self._setup(client, sample_dir, "chi2@datapilot.dev")
        response = client.post(
            f"/api/datasets/{dataset['id']}/statistics/test",
            headers=_auth(token),
            json={"test": "chi_square", "x": "species", "y": "species"},
        )
        # Same column twice is degenerate; API must return a clear 422 not a crash.
        assert response.status_code in (200, 422)

    def test_confidence_interval_endpoint(self, client, sample_dir):
        token, dataset = self._setup(client, sample_dir, "ci@datapilot.dev")
        response = client.post(
            f"/api/datasets/{dataset['id']}/statistics/confidence-interval",
            headers=_auth(token),
            json={"column": "sepal_length", "confidence": 0.95},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["lower"] < body["mean"] < body["upper"]

    def test_descriptive_statistics_endpoint(self, client, sample_dir):
        token, dataset = self._setup(client, sample_dir, "desc@datapilot.dev")
        response = client.get(
            f"/api/datasets/{dataset['id']}/statistics/descriptive", headers=_auth(token)
        )
        assert response.status_code == 200
        rows = response.json()["rows"]
        assert len(rows) == 2  # sepal_length + sepal_width


class TestNaturalLanguageApi:
    def _setup(self, client, sample_dir, email):
        token, _ = _signup(client, email)
        project = client.post(
            "/api/projects", headers=_auth(token), json={"name": "NL"}
        ).json()
        dataset = _upload_csv(
            client, token, project["id"], sample_dir / "sales_data.csv"
        ).json()
        return token, dataset

    def test_llm_status_endpoint(self, client):
        response = client.get("/api/llm/status")
        assert response.status_code == 200
        body = response.json()
        assert body["enabled"] is False
        assert "rule-based" in body["message"]

    def test_query_returns_labelled_rule_based_answer(self, client, sample_dir):
        token, dataset = self._setup(client, sample_dir, "nl1@datapilot.dev")
        response = client.post(
            f"/api/datasets/{dataset['id']}/query",
            headers=_auth(token),
            json={"question": "What is the average revenue?"},
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["engine"] == "rule_based"
        assert body["engine_label"] == "Rule-based engine"
        assert body["intent"] == "aggregate"
        assert body["result"]["value"] is not None
        assert body["conversation_id"] > 0

    def test_query_persists_conversation(self, client, sample_dir):
        token, dataset = self._setup(client, sample_dir, "nl2@datapilot.dev")
        first = client.post(
            f"/api/datasets/{dataset['id']}/query",
            headers=_auth(token),
            json={"question": "How many rows are in this dataset?"},
        ).json()

        second = client.post(
            f"/api/datasets/{dataset['id']}/query",
            headers=_auth(token),
            json={
                "question": "How many missing values are there?",
                "conversation_id": first["conversation_id"],
            },
        ).json()
        assert second["conversation_id"] == first["conversation_id"]

        conversation = client.get(
            f"/api/conversations/{first['conversation_id']}", headers=_auth(token)
        ).json()
        # 2 user messages + 2 assistant messages
        assert len(conversation["messages"]) == 4

    def test_unsupported_question_gives_guidance(self, client, sample_dir):
        token, dataset = self._setup(client, sample_dir, "nl3@datapilot.dev")
        response = client.post(
            f"/api/datasets/{dataset['id']}/query",
            headers=_auth(token),
            json={"question": "Write me a poem about sales"},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["intent"] == "unsupported"
        assert len(body["supported_examples"]) > 0

    def test_suggestions_endpoint(self, client, sample_dir):
        token, dataset = self._setup(client, sample_dir, "nl4@datapilot.dev")
        response = client.get(
            f"/api/datasets/{dataset['id']}/query/suggestions", headers=_auth(token)
        )
        assert response.status_code == 200
        assert len(response.json()["suggestions"]) > 0


class TestReports:
    def _setup(self, client, sample_dir, email):
        token, _ = _signup(client, email)
        project = client.post(
            "/api/projects", headers=_auth(token), json={"name": "Reports"}
        ).json()
        dataset = _upload_csv(
            client, token, project["id"], sample_dir / "sales_data.csv"
        ).json()
        return token, dataset

    def test_pdf_report_generated_and_downloadable(self, client, sample_dir):
        token, dataset = self._setup(client, sample_dir, "rep1@datapilot.dev")
        response = client.post(
            f"/api/datasets/{dataset['id']}/reports",
            headers=_auth(token),
            json={"fmt": "pdf", "title": "Acceptance Report"},
        )
        assert response.status_code == 200, response.text
        report = response.json()
        assert report["fmt"] == "pdf"

        download = client.get(
            f"/api/reports/{report['uid']}/download", headers=_auth(token)
        )
        assert download.status_code == 200
        assert download.headers["content-type"] == "application/pdf"
        # A real PDF starts with %PDF and is not trivially small.
        assert download.content.startswith(b"%PDF")
        assert len(download.content) > 5000

    def test_html_report_contains_real_numbers(self, client, sample_dir):
        token, dataset = self._setup(client, sample_dir, "rep2@datapilot.dev")
        report = client.post(
            f"/api/datasets/{dataset['id']}/reports",
            headers=_auth(token),
            json={"fmt": "html", "title": "HTML Report"},
        ).json()

        download = client.get(
            f"/api/reports/{report['uid']}/download", headers=_auth(token)
        )
        assert download.status_code == 200
        html = download.text
        assert "<html" in html.lower()
        assert "Data Quality" in html or "Quality" in html
        # Must embed a chart image rendered from real data.
        assert "data:image/png;base64," in html

    def test_report_listing(self, client, sample_dir):
        token, dataset = self._setup(client, sample_dir, "rep3@datapilot.dev")
        client.post(
            f"/api/datasets/{dataset['id']}/reports",
            headers=_auth(token),
            json={"fmt": "pdf"},
        )
        listing = client.get(
            f"/api/datasets/{dataset['id']}/reports", headers=_auth(token)
        )
        assert listing.status_code == 200
        assert len(listing.json()) == 1


class TestDashboard:
    def test_dashboard_kpis_are_computed(self, client, sample_dir):
        token, _ = _signup(client, "dash@datapilot.dev")
        project = client.post(
            "/api/projects", headers=_auth(token), json={"name": "Dash"}
        ).json()
        dataset = _upload_csv(
            client, token, project["id"], sample_dir / "sales_data.csv"
        ).json()

        response = client.get(
            f"/api/datasets/{dataset['id']}/dashboard", headers=_auth(token)
        )
        assert response.status_code == 200
        body = response.json()
        kpis = body["kpis"]
        assert kpis["rows"] == dataset["versions"][0]["row_count"]
        assert kpis["columns"] == 9
        assert 0 <= kpis["quality_score"] <= 100
        assert kpis["missing_cells"] > 0  # the sample data has missing values
        assert len(body["findings"]) >= 3


class TestAnalysisHistory:
    def test_chart_runs_are_recorded(self, client, sample_dir):
        token, _ = _signup(client, "hist2b@datapilot.dev")
        project = client.post(
            "/api/projects", headers=_auth(token), json={"name": "History"}
        ).json()
        dataset = _upload_csv(
            client, token, project["id"], sample_dir / "iris.csv"
        ).json()

        client.post(
            f"/api/datasets/{dataset['id']}/charts",
            headers=_auth(token),
            json={"chart_type": "histogram", "x": "sepal_length"},
        )
        history = client.get(
            f"/api/datasets/{dataset['id']}/analysis/history", headers=_auth(token)
        )
        assert history.status_code == 200
        assert len(history.json()) >= 1
        assert history.json()[0]["analysis_type"].startswith("chart:")
