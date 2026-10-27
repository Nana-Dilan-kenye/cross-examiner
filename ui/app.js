/* Cross-Examiner investigation page.
 *
 * The page calls the API that serves it:
 *   GET  /health            the mode, and what is reachable
 *   GET  /examples          the requests in input_examples/
 *   POST /run               one investigation
 *   GET  /traces/<run_id>   the trace of that run
 *
 * Every figure, name and sentence of a result comes from one of those
 * responses. API text is written with textContent, never as HTML. A new run
 * clears the previous result first, so an old answer is never shown as new.
 *
 * The functions above the DOM section have no side effects. They are
 * exported for the Node tests in tests/test_ui.py.
 */
var CrossExaminerUI = (function () {
  "use strict";

  var RUN_TIMEOUT_MS = 300000;
  var QUICK_TIMEOUT_MS = 30000;
  var RECOVERY =
    "Start the service and try again: python3 -m src.app for live mode, " +
    "or SAMPLE_MODE=true python3 -m src.app for the offline sample.";

  // What each verification scope means, as the README defines them.
  var SCOPES = [
    ["INDEPENDENT_VERIFICATION", "The value was checked against the source's own published table, from a different series than the one it came from."],
    ["INDEPENDENT_MEASUREMENT", "A measurement that does not derive from the numbers it is compared with, such as a household survey rather than administrative reporting. It is independent evidence about the level, not a verification of the other numbers."],
    ["SELF_CONSISTENCY", "The value was compared with the extract it came from, or with another publication of the same series. It shows the extraction worked."],
    ["DOCUMENT_PRESENCE", "The document was retrieved so it could be inspected. Its contents are not verified."],
    ["CONTEXT_ONLY", "Context only. Context is never treated as proof."]
  ];

  // What the confidence levels mean, as src/runner.py defines them.
  var CONFIDENCE = [
    ["high", "An independent source confirmed both published values."],
    ["moderate", "An independent measurement contradicts one of them, so the finding is characterised but not settled."],
    ["low", "The numbers were only checked against their own publications."],
    ["none", "The finding was withheld."]
  ];

  // The agents in a trace, and what each one does, as the README describes them.
  var ROLES = {
    orchestrator: "runs the loop and records what happened",
    investigator: "proposes which evidence to gather next; it never decides",
    critic: "checks each number against the publication it came from, and raises challenges",
    arbiter: "makes the deterministic decision",
    adjudicator: "gates the model's proposed disposition",
    memory: "reads and writes the persistent memory"
  };

  // ---------------------------------------------------------------------------
  // Pure functions
  // ---------------------------------------------------------------------------

  function isNumber(value) {
    return typeof value === "number" && isFinite(value);
  }

  // A value from the API, as text. Missing values are said to be missing,
  // never filled in.
  function formatValue(value) {
    if (value === undefined || value === null || value === "") {
      return "not reported";
    }
    if (isNumber(value)) {
      return String(Math.round(value * 100) / 100);
    }
    if (typeof value === "boolean") {
      return value ? "yes" : "no";
    }
    return String(value);
  }

  function isHttpUrl(value) {
    return typeof value === "string" && /^https?:\/\/[^\s]+$/i.test(value);
  }

  // Only http(s) links are followed. A javascript: or data: URL from the
  // API is shown as text.
  function safeHref(value) {
    return isHttpUrl(value) ? value : null;
  }

  // What kind of figure a lineage row is. Only the API's own fields are read.
  function classifyFigure(item) {
    item = item || {};
    if (item.is_derived === true) {
      return {
        tone: "derived",
        label: "Republication, not independent",
        note: "A copy of an existing series, so it is not a separate line of evidence."
      };
    }
    if (item.verification_scope === "INDEPENDENT_VERIFICATION") {
      return {
        tone: "independent",
        label: "Independently verified",
        note: "Checked against the source's own table."
      };
    }
    if (item.verification_scope === "INDEPENDENT_MEASUREMENT") {
      return {
        tone: "independent",
        label: "Independent measurement",
        note: "Not derived from the figures it is compared with."
      };
    }
    if (
      item.verification_scope === "SELF_CONSISTENCY" ||
      item.verification_scope === "DOCUMENT_PRESENCE" ||
      item.verification_scope === "CONTEXT_ONLY"
    ) {
      return {
        tone: "published",
        label: "Published, not independent",
        note: "Not independently verified."
      };
    }
    return { tone: "unknown", label: "Type not reported", note: "" };
  }

  // What a finding's data_kind means. Sample and synthetic data are named
  // as such wherever they are shown.
  function describeDataKind(kind) {
    var text = String(kind || "");
    if (text.indexOf("sample:") === 0) {
      if (text.slice("sample:".length) === "synthetic") {
        return {
          tone: "sample",
          label: "Synthetic sample data (offline)",
          note: "Generated records, served in sample mode. They are never evidence about a real country."
        };
      }
      return {
        tone: "sample",
        label: "Sample data (offline)",
        note: "Cached local files, read without the network. This is not a live read of the evidence layer."
      };
    }
    if (text === "synthetic") {
      return {
        tone: "synthetic",
        label: "Synthetic (generated)",
        note: "Generated records. They are never evidence about a real country."
      };
    }
    if (text === "observed") {
      return {
        tone: "published",
        label: "Observed (published)",
        note: "Real published figures, not generated records."
      };
    }
    return {
      tone: "published",
      label: text || "Data kind not reported",
      note: ""
    };
  }

  // The verdict shown at the top of the results. REVIEW is shown whenever
  // the API returns it, for the run or for any finding.
  function verdictFor(payload) {
    payload = payload || {};
    var findings = payload.findings || [];
    var anyReview = findings.some(function (finding) {
      return finding && finding.review_status === "REVIEW";
    });
    if (payload.status === "review" || anyReview) {
      return {
        tone: "review",
        label: "REVIEW",
        text: "A person has to decide. The evidence, the trace and the open questions are below. Cross-Examiner has not settled which published figure is correct."
      };
    }
    if (payload.status === "resolved") {
      return {
        tone: "resolved",
        label: "RESOLVED",
        text: "Every finding was accepted or rejected by the deterministic rules. This still supports a decision; it does not certify a true figure."
      };
    }
    if (payload.status === "abstained") {
      return {
        tone: "neutral",
        label: "ABSTAINED",
        text: "The system declined to give a conclusion for at least one finding. The open questions are under Conclusion and review status."
      };
    }
    if (payload.status === "no_findings") {
      return {
        tone: "neutral",
        label: "NO FINDINGS",
        text: "The request matched no comparable figures in the evidence that was read. Nothing has been concluded."
      };
    }
    return {
      tone: "neutral",
      label: String(payload.status || "UNKNOWN").toUpperCase(),
      text: "The API returned a status this page does not recognise. The raw response is under Run details."
    };
  }

  // The kind of one trace event, from the agent that wrote it.
  function eventKind(event) {
    event = event || {};
    var agent = event.agent_name || "";
    var action = String(event.action || "");
    if (agent === "memory" || action.indexOf("memory.") === 0 || action.indexOf("recall.") === 0) {
      return "memory";
    }
    if (agent === "critic") {
      return "critique";
    }
    if (agent === "arbiter") {
      return "arbitration";
    }
    if (agent === "adjudicator") {
      return "adjudication";
    }
    if (agent === "investigator") {
      return "investigation";
    }
    return "lifecycle";
  }

  // The badges an event earns from the fields it actually carries.
  function eventBadges(event) {
    event = event || {};
    var badges = [];
    if (eventKind(event) === "memory") {
      badges.push({ tone: "memory", label: "Memory" });
    }
    if (event.changed_action) {
      badges.push({ tone: "memory", label: "Changed the plan" });
    }
    if (event.prior_conflict === true) {
      badges.push({ tone: "memory", label: "Earlier conflict recalled" });
    }
    if (isNumber(event.retry_count) && event.retry_count > 0) {
      badges.push({ tone: "retry", label: "Retry " + event.retry_count });
    }
    if (event.would_change_verdict === true) {
      badges.push({ tone: "warn", label: "Would change the verdict" });
    }
    return badges;
  }

  // Counts over a trace, for the line above the timeline.
  function traceSummary(events) {
    var agents = {};
    var summary = { events: events.length, agents: [], handovers: 0, memory: 0, retries: 0 };
    events.forEach(function (event) {
      if (event.agent_name) {
        agents[event.agent_name] = true;
      }
      if (event.target_agent) {
        summary.handovers += 1;
      }
      if (eventKind(event) === "memory") {
        summary.memory += 1;
      }
      if (isNumber(event.retry_count) && event.retry_count > 0) {
        summary.retries += 1;
      }
    });
    summary.agents = Object.keys(agents).sort();
    return summary;
  }

  // The request body for POST /run, from the form's fields. Blank scope
  // fields are left out, so the API does not narrow on them.
  function buildRequest(fields) {
    var request = { question: String(fields.question || "").trim() };
    ["country", "antigen", "year"].forEach(function (name) {
      var value = String(fields[name] || "").trim();
      if (value) {
        request[name] = value;
      }
    });
    request.use_memory = true;
    request.remember = fields.remember === true;
    return request;
  }

  // The message for a request the API would refuse, or null.
  function requestProblem(request) {
    if (request.question) {
      return null;
    }
    if (request.country && request.antigen && request.year) {
      return null;
    }
    return "Type a question, or fill in country, antigen and year.";
  }

  // ---------------------------------------------------------------------------
  // DOM helpers. Text is always added with textContent.
  // ---------------------------------------------------------------------------

  function $(id) {
    return document.getElementById(id);
  }

  function isNode(value) {
    return Boolean(value) && typeof value === "object" && typeof value.nodeType === "number";
  }

  function appendAll(node, children) {
    (Array.isArray(children) ? children : [children]).forEach(function (child) {
      if (child === undefined || child === null || child === false) {
        return;
      }
      if (Array.isArray(child)) {
        appendAll(node, child);
        return;
      }
      node.appendChild(isNode(child) ? child : document.createTextNode(String(child)));
    });
    return node;
  }

  function h(tag, props, children) {
    var node = document.createElement(tag);
    Object.keys(props || {}).forEach(function (key) {
      var value = props[key];
      if (value === undefined || value === null || value === false) {
        return;
      }
      if (key === "className") {
        node.className = value;
      } else if (value === true) {
        node.setAttribute(key, "");
      } else {
        node.setAttribute(key, String(value));
      }
    });
    return appendAll(node, children);
  }

  function fill(container, children) {
    container.textContent = "";
    return appendAll(container, children);
  }

  // Label and value pairs as a definition list.
  function facts(rows) {
    var list = h("dl", { className: "facts" }, []);
    rows.forEach(function (row) {
      var value = row[1];
      list.appendChild(h("dt", {}, row[0]));
      list.appendChild(h("dd", {}, value === undefined || value === null || value === "" ? "not reported" : value));
    });
    return list;
  }

  function linkTo(url, label) {
    var href = safeHref(url);
    if (!href) {
      return label || formatValue(url);
    }
    return h("a", { href: href, target: "_blank", rel: "noopener noreferrer" }, label || href);
  }

  function percent(value) {
    return isNumber(value) ? formatValue(value) + "%" : "not reported";
  }

  function tag(label, tone) {
    return h("span", { className: "tag tag-" + tone }, label);
  }

  function roleTag(name) {
    var known = Object.prototype.hasOwnProperty.call(ROLES, name);
    return h("span", { className: "role" + (known ? " role-" + name : "") }, formatValue(name));
  }

  function findingTitle(finding) {
    var parts = [finding.country, finding.antigen, finding.year].filter(function (part) {
      return part !== undefined && part !== null && part !== "";
    });
    return parts.length ? parts.join(" · ") : "Finding";
  }

  // ---------------------------------------------------------------------------
  // Network
  // ---------------------------------------------------------------------------

  function apiError(message, kind, status) {
    var error = new Error(message);
    error.kind = kind;
    error.status = status;
    return error;
  }

  // One request to the API. Fails with a message the page can show.
  async function requestJson(path, options) {
    options = options || {};
    var controller = typeof AbortController === "function" ? new AbortController() : null;
    var timer = controller
      ? setTimeout(function () { controller.abort(); }, options.timeout || QUICK_TIMEOUT_MS)
      : null;
    var init = { method: options.method || "GET", headers: { Accept: "application/json" }, cache: "no-store" };
    if (options.body !== undefined) {
      init.body = options.body;
      init.headers["Content-Type"] = "application/json";
    }
    if (controller) {
      init.signal = controller.signal;
    }

    var response;
    var body = null;
    try {
      try {
        response = await fetch(path, init);
      } catch (error) {
        var timedOut = Boolean(error) && error.name === "AbortError";
        throw apiError(
          timedOut
            ? "The request to " + path + " timed out."
            : "The API did not answer the request to " + path + ".",
          "network",
          0
        );
      }
      try {
        body = await response.json();
      } catch (error) {
        body = null;
      }
    } finally {
      if (timer) {
        clearTimeout(timer);
      }
    }

    if (!response.ok) {
      var message = body && (body.error || body.message)
        ? String(body.error || body.message)
        : "The API answered with HTTP " + response.status + ".";
      if (body && body.detail) {
        message += " (" + String(body.detail) + ")";
      }
      throw apiError(message, "http", response.status);
    }
    if (body === null) {
      throw apiError("The API answered " + path + " with something that is not JSON.", "invalid", response.status);
    }
    return body;
  }

  // ---------------------------------------------------------------------------
  // Rendering: the mode banner and the examples
  // ---------------------------------------------------------------------------

  function renderHealth(report) {
    var banner = $("mode-banner");
    var components = report.components || {};
    if (report.sample_mode) {
      banner.className = "banner banner-sample";
      fill(banner, [
        h("strong", {}, "Sample mode (offline). "),
        "Answers come from the cached local files in data/. No network call, no Zetaris layer and no memory store is used, and every finding is labelled as sample data."
      ]);
      setRememberAvailable(false);
      return;
    }
    var layer = components.zetaris_usl || {};
    var memory = components.memory || {};
    var rows = layer.rows === undefined || layer.rows === null ? "" : " (" + layer.rows + " rows)";
    banner.className = "banner banner-live";
    setRememberAvailable(true);
    fill(banner, [
      h("strong", {}, "Live mode. "),
      "Evidence layer: " + (layer.reachable ? "reachable" + rows : "not reachable") + ". " +
        "Memory: " + (memory.available ? "available" : "unavailable") + ". " +
        "If the layer is not reachable, a run falls back to the local files, and its results say so."
    ]);
  }

  // Sample mode does not use the memory store, so the page offers no way to
  // write to it there.
  function setRememberAvailable(available) {
    var box = $("remember");
    box.disabled = !available;
    if (!available) {
      box.checked = false;
    }
    $("remember-hint").textContent = available
      ? ""
      : "Not available in sample mode, which does not use the memory store.";
  }

  function renderHealthFailure(error) {
    var banner = $("mode-banner");
    banner.className = "banner banner-error";
    fill(banner, [h("strong", {}, "The API is not answering. "), error.message + " " + RECOVERY]);
  }

  function fillForm(request) {
    $("question").value = request.question || "";
    $("country").value = request.country || "";
    $("antigen").value = request.antigen || "";
    $("year").value = request.year || "";
    $("question").focus();
  }

  function renderExamples(items) {
    var box = $("examples");
    if (!items.length) {
      fill(box, [h("p", { className: "muted" }, "No example requests were found in input_examples/.")]);
      return;
    }
    fill(box, items.map(function (item) {
      var request = item.request || {};
      var scope = [request.country, request.antigen, request.year].filter(Boolean).join(" ");
      // A request that asks for the local files is labelled as such, so two
      // otherwise identical scopes are told apart on the page.
      var title = request.source === "local" && scope
        ? "Sample mode · " + scope
        : scope || "All published figures";
      var button = h("button", {
        type: "button",
        className: "chip",
        title: request.question || ""
      }, [
        h("strong", {}, title),
        h("span", {}, request.question || formatValue(item.file))
      ]);
      button.addEventListener("click", function () {
        fillForm(request);
      });
      return button;
    }));
  }

  // ---------------------------------------------------------------------------
  // Rendering: B. Evidence comparison
  // ---------------------------------------------------------------------------

  function scopeLegend() {
    return h("details", {}, [
      h("summary", {}, "What the verification scopes mean"),
      facts(SCOPES.map(function (pair) {
        return [h("code", {}, pair[0]), pair[1]];
      })),
      h("p", { className: "hint" }, "Only INDEPENDENT_VERIFICATION can support a positive disposition.")
    ]);
  }

  function lineageRow(item) {
    var figure = classifyFigure(item);
    var derived = item.is_derived === true ? "yes, a copy of an existing series" :
      item.is_derived === false ? "no" : "not reported";
    var rowClass = figure.tone === "derived" ? "row-derived" :
      figure.tone === "independent" ? "row-independent" : "";
    return h("tr", { className: rowClass }, [
      h("td", {}, [
        h("strong", {}, formatValue(item.measure)),
        h("span", { className: "cell-sub" }, "kind: " + formatValue(item.measurement_kind))
      ]),
      h("td", {}, formatValue(item.value)),
      h("td", {}, [
        tag(figure.label, figure.tone === "unknown" ? "published" : figure.tone),
        figure.note ? h("span", { className: "cell-sub" }, figure.note) : null
      ]),
      h("td", {}, [
        h("strong", {}, formatValue(item.source_name)),
        h("span", { className: "cell-sub" }, "ID: " + formatValue(item.source_id)),
        item.source_ref ? h("span", { className: "cell-sub" }, linkTo(item.source_ref, "source page")) : null
      ]),
      h("td", {}, [
        h("strong", {}, formatValue(item.origin)),
        h("span", { className: "cell-sub" }, formatValue(item.origin_label))
      ]),
      h("td", {}, [
        h("span", { className: "cell-sub" }, "Derived: " + derived),
        h("span", {}, ["Scope: ", h("code", {}, formatValue(item.verification_scope))])
      ])
    ]);
  }

  function lineageTable(lineage) {
    if (!lineage.length) {
      return h("p", { className: "muted" }, "No figures were returned for this finding.");
    }
    return h("div", { className: "table-wrap" }, [
      h("table", {}, [
        h("caption", {}, "Each reported figure, with its lineage"),
        h("thead", {}, [
          h("tr", {}, [
            h("th", { scope: "col" }, "Figure"),
            h("th", { scope: "col" }, "Coverage (%)"),
            h("th", { scope: "col" }, "Type"),
            h("th", { scope: "col" }, "Source"),
            h("th", { scope: "col" }, "Origin"),
            h("th", { scope: "col" }, "Derived and scope")
          ])
        ]),
        h("tbody", {}, lineage.map(lineageRow))
      ])
    ]);
  }

  function conflictItem(conflict) {
    return h("li", {}, [
      h("strong", {}, formatValue(conflict.code)),
      " · " + formatValue(conflict.measure_a) + " " + formatValue(conflict.value_a) +
        " against " + formatValue(conflict.measure_b) + " " + formatValue(conflict.value_b) +
        ", a gap of " + formatValue(conflict.gap_percentage_points) + " percentage points.",
      h("span", { className: "event-meta" }, " Origins: " + formatValue(conflict.origin_a) + " and " + formatValue(conflict.origin_b) + "."),
      conflict.note ? h("p", { className: "event-meta" }, String(conflict.note)) : null
    ]);
  }

  function checkItem(item) {
    return h("li", {}, [
      h("strong", {}, formatValue(item.evidence_id) + " · " + formatValue(item.kind)),
      " " + formatValue(item.name) + ". Status " + formatValue(item.status) + ", scope " + formatValue(item.scope) + ". ",
      safeHref(item.url) ? linkTo(item.url, "source") : null
    ]);
  }

  function evidenceCard(finding) {
    var kind = describeDataKind(finding.data_kind);
    var measures = finding.measures || {};
    var a = measures.a || {};
    var b = measures.b || {};
    var lineage = finding.lineage || [];
    var conflicts = finding.conflicts || [];
    var uncertainties = finding.uncertainties || [];
    var checks = finding.evidence || [];
    var gap = isNumber(finding.gap_percentage_points)
      ? formatValue(finding.gap_percentage_points) + " percentage points"
      : "not reported";

    return h("article", { className: "card" }, [
      h("div", { className: "card-head" }, [
        h("h3", {}, findingTitle(finding)),
        tag(kind.label, kind.tone)
      ]),
      kind.note ? h("p", { className: "muted" }, kind.note) : null,
      h("p", {}, [
        "Year " + formatValue(finding.year) + ". Gap: " + gap + " between " +
          formatValue(a.measure) + " (" + formatValue(a.value) + ") and " +
          formatValue(b.measure) + " (" + formatValue(b.value) + ")."
      ]),
      lineageTable(lineage),
      h("h3", {}, "Conflicts"),
      conflicts.length
        ? h("ul", { className: "plain" }, conflicts.map(conflictItem))
        : h("p", { className: "muted" }, "No conflict was recorded for this finding."),
      h("h3", {}, "Relevant uncertainty"),
      uncertainties.length
        ? h("ul", { className: "plain" }, uncertainties.map(function (text) { return h("li", {}, String(text)); }))
        : h("p", { className: "muted" }, "None was returned for this finding."),
      h("details", {}, [
        h("summary", {}, "Evidence checks (" + checks.length + ")"),
        checks.length
          ? h("ul", { className: "plain" }, checks.map(checkItem))
          : h("p", { className: "muted" }, "No evidence checks were returned."),
      ]),
      scopeLegend()
    ]);
  }

  function renderEvidence(payload) {
    var findings = payload.findings || [];
    var body = $("evidence-body");
    if (!findings.length) {
      fill(body, [h("p", {}, "No comparable figures were found for this request, so there is nothing to compare. The evidence that was read is listed under Run details.")]);
      return;
    }
    fill(body, findings.map(evidenceCard));
  }

  // ---------------------------------------------------------------------------
  // Rendering: C. Investigation trace
  // ---------------------------------------------------------------------------

  function roleLegend() {
    return h("div", { className: "legend" }, Object.keys(ROLES).map(function (name) {
      return h("p", { className: "muted" }, [roleTag(name), " " + ROLES[name]]);
    }));
  }

  function traceItem(event) {
    var kind = eventKind(event);
    var head = [roleTag(event.agent_name)];
    if (event.target_agent) {
      head.push(h("span", { className: "arrow", "aria-label": "hands over to" }, "→"));
      head.push(roleTag(event.target_agent));
    }
    head.push(h("code", { className: "event-action" }, formatValue(event.action)));
    eventBadges(event).forEach(function (badge) {
      head.push(tag(badge.label, badge.tone));
    });
    head.push(h("span", { className: "event-time" }, formatValue(event.timestamp)));

    var meta = [];
    if (event.status) {
      meta.push("status " + event.status);
    }
    if (event.iteration !== undefined && event.iteration !== null) {
      meta.push("iteration " + event.iteration);
    }
    if (isNumber(event.confidence)) {
      meta.push("confidence " + formatValue(event.confidence));
    }
    if (event.decision) {
      meta.push("decision " + event.decision);
    }
    if (event.changed_action) {
      meta.push("changed action " + formatValue(event.changed_action));
    }
    if (event.stop_reason) {
      meta.push("stop reason " + event.stop_reason);
    }

    return h("li", { className: "kind-" + kind }, [
      h("div", { className: "event-head" }, head),
      event.input_summary ? h("p", { className: "event-text" }, [h("strong", {}, "In: "), String(event.input_summary)]) : null,
      event.output_summary ? h("p", { className: "event-text" }, [h("strong", {}, "Out: "), String(event.output_summary)]) : null,
      meta.length ? h("p", { className: "event-meta" }, meta.join(" · ")) : null,
      h("details", {}, [
        h("summary", {}, "All fields of this event"),
        h("pre", {}, JSON.stringify(event, null, 2))
      ])
    ]);
  }

  function renderTrace(events) {
    var body = $("trace-body");
    if (!events.length) {
      fill(body, [h("p", {}, "The trace file has no events for this run.")]);
      return;
    }
    var summary = traceSummary(events);
    fill(body, [
      h("p", { className: "muted" },
        summary.events + " events · " + summary.agents.length + " agents (" + summary.agents.join(", ") +
        ") · " + summary.handovers + " handovers · " + summary.memory + " memory events · " +
        summary.retries + " with retries"),
      roleLegend(),
      h("ol", { className: "timeline", "aria-label": "Trace events in order" }, events.map(traceItem))
    ]);
  }

  async function loadTrace(runId) {
    fill($("trace-body"), [h("p", { className: "muted" }, "Loading the trace for run " + runId + "…")]);
    try {
      var data = await requestJson("/traces/" + encodeURIComponent(runId), { timeout: QUICK_TIMEOUT_MS });
      if (!current || current.run_id !== runId) {
        return;
      }
      renderTrace(data.events || []);
    } catch (error) {
      if (!current || current.run_id !== runId) {
        return;
      }
      fill($("trace-body"), [h("div", { className: "notice" }, [h("p", {}, "The trace could not be loaded: " + error.message)])]);
    }
  }

  // ---------------------------------------------------------------------------
  // Rendering: D. Conclusion and review status
  // ---------------------------------------------------------------------------

  function recommendationBlock(rec) {
    var caveats = rec.caveats || [];
    var gap = isNumber(rec.gap_percentage_points)
      ? "The two figures differ by " + formatValue(rec.gap_percentage_points) + " percentage points."
      : null;
    return h("div", { className: "card" }, [
      h("p", {}, [
        h("strong", {}, "Recommended for the coverage level: "),
        formatValue(rec.recommended_measure) + " = " + percent(rec.recommended_value) + "."
      ]),
      h("p", { className: "muted" }, "Source: " + formatValue(rec.recommended_source) + " (ID " + formatValue(rec.recommended_source_id) + ")."),
      h("p", {}, [
        h("strong", {}, "Not recommended as the coverage level: "),
        formatValue(rec.not_recommended_measure) + " = " + percent(rec.not_recommended_value) + "."
      ]),
      gap ? h("p", {}, gap) : null,
      rec.basis ? h("p", {}, [h("strong", {}, "Basis: "), String(rec.basis)]) : null,
      caveats.length
        ? h("div", {}, [
            h("strong", {}, "Caveats"),
            h("ul", { className: "plain" }, caveats.map(function (text) { return h("li", {}, String(text)); }))
          ])
        : null
    ]);
  }

  function memoryBlock(recall) {
    var ids = recall.memory_ids || [];
    return h("div", {}, [
      h("h3", {}, "Memory from earlier runs"),
      facts([
        ["Earlier conflict recalled", formatValue(recall.has_prior_conflict)],
        ["Earlier disposition", formatValue(recall.prior_disposition)],
        ["Preferred next action", formatValue(recall.preferred_action)],
        ["Memory items used", ids.length ? String(ids.length) : "none"],
        ["Effect on the plan", recall.effect ? String(recall.effect) : "none recorded"]
      ])
    ]);
  }

  function conclusionBlock(finding) {
    var uncertainties = finding.uncertainties || [];
    var review = finding.review_status;
    return h("article", { className: "card" }, [
      h("h3", {}, findingTitle(finding)),
      h("p", {}, [
        tag("Review status: " + formatValue(review), review === "REVIEW" ? "review" : "published"),
        tag("Confidence: " + formatValue(finding.confidence), "published"),
        tag("Decision: " + formatValue(finding.decision), "published")
      ]),
      h("p", {}, [h("strong", {}, "Why: "), formatValue(finding.reason)]),
      finding.recommendation
        ? recommendationBlock(finding.recommendation)
        : h("div", { className: "notice" }, [
            h("p", {}, "No recommendation was returned for this finding, so this page does not suggest a figure.")
          ]),
      h("h3", {}, "Unresolved uncertainties"),
      uncertainties.length
        ? h("ul", { className: "plain" }, uncertainties.map(function (text) { return h("li", {}, String(text)); }))
        : h("p", { className: "muted" }, "None was returned for this finding."),
      finding.memory_recall ? memoryBlock(finding.memory_recall) : null
    ]);
  }

  function renderConclusion(payload) {
    var findings = payload.findings || [];
    var blocks = findings.length
      ? findings.map(conclusionBlock)
      : [h("p", {}, "No finding was produced, so there is no conclusion to review.")];
    blocks.push(
      h("div", { className: "notice" }, [
        h("p", {}, [
          h("strong", {}, "A person decides. "),
          "Cross-Examiner supports human decision-making. It does not independently certify which vaccination figure is true; it reports what the evidence supports and what it does not."
        ])
      ]),
      h("details", {}, [
        h("summary", {}, "What the confidence levels mean"),
        facts(CONFIDENCE.map(function (pair) {
          return [h("code", {}, pair[0]), pair[1]];
        }))
      ])
    );
    fill($("conclusion-body"), blocks);
  }

  function renderVerdict(payload) {
    var verdict = verdictFor(payload);
    fill($("verdict"), [
      h("span", { className: "verdict-label" }, verdict.label),
      h("p", {}, verdict.text),
      h("p", {}, [
        "Go to: ",
        h("a", { href: "#evidence" }, "Evidence comparison"), " · ",
        h("a", { href: "#trace" }, "Investigation trace"), " · ",
        h("a", { href: "#conclusion" }, "Conclusion and review status"), " · ",
        h("a", { href: "#run" }, "Run details")
      ])
    ]);
    $("verdict").className = "verdict verdict-" + verdict.tone;
  }

  // ---------------------------------------------------------------------------
  // Rendering: E. Run details
  // ---------------------------------------------------------------------------

  function downloadJson(payload) {
    var blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
    var url = URL.createObjectURL(blob);
    var name = String(payload.run_id || "run").replace(/[^A-Za-z0-9._-]/g, "_");
    var link = h("a", { href: url, download: "cross-examiner-" + name + ".json" });
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    setTimeout(function () { URL.revokeObjectURL(url); }, 2000);
  }

  function renderRun(payload, elapsed) {
    var model = payload.model || {};
    var memory = payload.memory || {};
    var layers = payload.semantic_layer || [];
    var actions = payload.executed_actions || [];
    var body = $("run-body");

    var modelText = [formatValue(model.status), model.model ? String(model.model) : null,
      "calls " + formatValue(model.calls), model.note ? String(model.note) : null]
      .filter(Boolean).join(" · ");
    var memoryText = (memory.available ? "available" : "not available") +
      ", recalled " + formatValue(memory.memories) + ", stored " + formatValue(memory.stored) +
      (memory.error ? ", error: " + String(memory.error) : "");

    var download = h("button", { type: "button", className: "secondary" }, "Download the raw JSON");
    download.addEventListener("click", function () { downloadJson(payload); });

    fill(body, [
      facts([
        ["Run ID", payload.run_id],
        ["Trace ID", payload.trace_id],
        ["Trace file", payload.log_file || payload.trace],
        ["Mode", formatValue(payload.mode) + (payload.sample_mode ? " (sample mode is on)" : "")],
        ["Execution time (server)", isNumber(payload.execution_time_seconds) ? payload.execution_time_seconds + " s" : null],
        ["Round trip (this page)", elapsed ? elapsed + " s" : null],
        ["Stop reason", payload.stop_reason],
        ["Stop detail", payload.stop_detail],
        ["Agents", (payload.agents || []).join(", ") || null],
        ["Model", modelText],
        ["Memory", memoryText]
      ]),
      h("h3", {}, "Evidence sources read"),
      layers.length
        ? h("ul", { className: "plain" }, layers.map(function (layer) {
            return h("li", {}, [
              h("strong", {}, formatValue(layer.source_id)),
              " · " + formatValue(layer.records) + " records · origin " + formatValue(layer.origin) +
                (layer.read_from ? " · read from " + String(layer.read_from) : "") +
                (layer.reason ? " · " + String(layer.reason) : "")
            ]);
          }))
        : h("p", { className: "muted" }, "The response lists no evidence sources."),
      h("h3", {}, "Actions executed"),
      actions.length
        ? h("ul", { className: "plain" }, actions.map(function (action) {
            return h("li", {}, [
              "Iteration " + formatValue(action.iteration) + ": ",
              h("code", {}, formatValue(action.action)),
              " on " + formatValue(action.finding) + " → " + formatValue(action.outcome) +
                (action.stop_reason ? " (" + String(action.stop_reason) + ")" : "")
            ]);
          }))
        : h("p", { className: "muted" }, "No evidence-retrieval action was executed."),
      h("div", { className: "actions" }, [
        download,
        h("a", {
          href: "/traces/" + encodeURIComponent(payload.run_id),
          target: "_blank",
          rel: "noopener noreferrer"
        }, "Open the trace as JSON")
      ]),
      h("details", {}, [
        h("summary", {}, "Raw JSON response"),
        h("pre", {}, JSON.stringify(payload, null, 2))
      ])
    ]);
  }

  // ---------------------------------------------------------------------------
  // The investigation
  // ---------------------------------------------------------------------------

  // The result on the page, or null. A trace that arrives after a newer run
  // has started is dropped.
  var current = null;

  function readFields() {
    return {
      question: $("question").value,
      country: $("country").value,
      antigen: $("antigen").value,
      year: $("year").value,
      remember: $("remember").checked
    };
  }

  function setBusy(busy) {
    var button = $("investigate-button");
    button.disabled = busy;
    button.textContent = busy ? "Investigating…" : "Investigate";
    $("investigate-form").setAttribute("aria-busy", busy ? "true" : "false");
  }

  function clearOutput() {
    current = null;
    var panel = $("error-panel");
    panel.hidden = true;
    fill(panel, []);
    $("results").hidden = true;
    var rail = $("sectionnav");
    if (rail) {
      rail.hidden = true;
    }
    setSectionNow(null);
  }

  // ---------------------------------------------------------------------------
  // Page chrome: the section rail and the back-to-top button.
  //
  // Text-free UX helpers. Everything is feature-detected, so an old browser
  // just gets plain anchors and no observer.
  // ---------------------------------------------------------------------------

  var railObserver = null;

  function setSectionNow(id) {
    var rail = $("sectionnav");
    if (!rail) {
      return;
    }
    Array.prototype.forEach.call(rail.querySelectorAll("a.rail-link"), function (link) {
      var active = id !== null && link.getAttribute("href") === "#" + id;
      if (active) {
        link.classList.add("is-active");
      } else {
        link.classList.remove("is-active");
      }
    });
  }

  function enableChrome() {
    var rail = $("sectionnav");
    var totop = $("totop");
    if (!rail && !totop) {
      return;
    }

    if ("IntersectionObserver" in window) {
      railObserver = new IntersectionObserver(function (entries) {
        // The first section the page is over, in document order.
        var visible = entries.filter(function (entry) {
          return entry.isIntersecting;
        });
        if (!visible.length) {
          return;
        }
        setSectionNow(visible[0].target.id);
      }, { rootMargin: "-56px 0px -60% 0px", threshold: 0.01 });

      ["evidence", "trace", "conclusion", "run"].forEach(function (id) {
        var section = $(id);
        if (section) {
          railObserver.observe(section);
        }
      });
    }

    if (totop) {
      totop.addEventListener("click", function () {
        var smooth = !window.matchMedia || !window.matchMedia("(prefers-reduced-motion: reduce)").matches;
        window.scrollTo({ top: 0, behavior: smooth ? "smooth" : "auto" });
      });
      var onScroll = function () {
        var down = window.scrollY > 800;
        if (down && totop.hidden) {
          totop.hidden = false;
          window.setTimeout(function () { totop.classList.add("is-visible"); }, 10);
        } else if (!down && !totop.hidden) {
          totop.classList.remove("is-visible");
          totop.hidden = true;
        }
      };
      window.addEventListener("scroll", onScroll, { passive: true });
    }
  }

  function showError(title, error) {
    var panel = $("error-panel");
    var hint = "";
    if (error.kind === "network") {
      hint = RECOVERY;
    } else if (error.kind === "http" && error.status >= 500) {
      hint = "The service reported a failure. Its terminal and the trace files in logs/ have the details.";
    } else if (error.kind === "http" && error.status === 400) {
      hint = "Change the request as the message says, then try again.";
    }
    fill(panel, [
      h("h2", {}, title),
      h("p", {}, error.message),
      hint ? h("p", {}, hint) : null
    ]);
    panel.hidden = false;
    panel.focus();
  }

  async function investigate() {
    var request = buildRequest(readFields());
    var problem = requestProblem(request);
    clearOutput();
    if (problem) {
      showError("Nothing to investigate", apiError(problem, "input", 0));
      return;
    }

    setBusy(true);
    var status = $("form-status");
    var started = Date.now();
    status.textContent = "Investigating…";
    var ticker = setInterval(function () {
      var seconds = Math.round((Date.now() - started) / 1000);
      status.textContent = "Investigating… " + seconds + " s. A live run can take a minute or more.";
    }, 1000);

    try {
      var payload = await requestJson("/run", {
        method: "POST",
        body: JSON.stringify(request),
        timeout: RUN_TIMEOUT_MS
      });
      var elapsed = ((Date.now() - started) / 1000).toFixed(1);
      current = payload;
      $("results").hidden = false;
      var rail = $("sectionnav");
      if (rail) {
        rail.hidden = false;
      }
      renderVerdict(payload);
      renderEvidence(payload);
      renderConclusion(payload);
      renderRun(payload, elapsed);
      status.textContent = "Finished in " + elapsed + " s. The results are below.";
      loadTrace(payload.run_id);
    } catch (error) {
      status.textContent = "";
      showError("The investigation did not complete", error);
    } finally {
      clearInterval(ticker);
      setBusy(false);
    }
  }

  function start() {
    $("investigate-form").addEventListener("submit", function (event) {
      event.preventDefault();
      investigate();
    });
    enableChrome();

    requestJson("/health", { timeout: QUICK_TIMEOUT_MS }).then(renderHealth, renderHealthFailure);

    requestJson("/examples", { timeout: QUICK_TIMEOUT_MS }).then(
      function (data) {
        renderExamples(data.requests || []);
      },
      function (error) {
        fill($("examples"), [h("p", { className: "muted" }, "The example questions could not be loaded: " + error.message)]);
      }
    );
  }

  return {
    classifyFigure: classifyFigure,
    describeDataKind: describeDataKind,
    verdictFor: verdictFor,
    eventKind: eventKind,
    eventBadges: eventBadges,
    traceSummary: traceSummary,
    formatValue: formatValue,
    safeHref: safeHref,
    buildRequest: buildRequest,
    requestProblem: requestProblem,
    start: start
  };
})();

if (typeof module !== "undefined" && module.exports) {
  module.exports = CrossExaminerUI;
}
if (typeof document !== "undefined") {
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", CrossExaminerUI.start);
  } else {
    CrossExaminerUI.start();
  }
}
