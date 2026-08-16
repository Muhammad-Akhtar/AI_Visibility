(function () {
  "use strict";

  function parseList(value) {
    return String(value || "")
      .split(/[\n,]+/)
      .map(function (item) {
        return item.trim();
      })
      .filter(Boolean);
  }

  function toast(message, kind) {
    var root = document.getElementById("toast-root");
    if (!root) return;
    var el = document.createElement("div");
    el.className = "toast toast-" + (kind || "success");
    el.setAttribute("data-toast", "");
    el.textContent = message;
    root.appendChild(el);
    window.setTimeout(function () {
      el.remove();
    }, 5200);
  }

  function dismissToasts() {
    document.querySelectorAll("[data-toast]").forEach(function (el) {
      window.setTimeout(function () {
        el.remove();
      }, 5200);
    });
  }

  function errorMessage(body, fallback) {
    if (body && body.error && body.error.message) {
      return body.error.message;
    }
    return fallback;
  }

  function enhanceChipField(textarea) {
    var wrap = document.createElement("div");
    wrap.className = "chip-field";
    var input = document.createElement("input");
    input.type = "text";
    input.placeholder = textarea.placeholder || "Add a domain";
    wrap.appendChild(input);
    textarea.hidden = true;
    textarea.after(wrap);

    function render() {
      wrap.querySelectorAll(".chip").forEach(function (chip) {
        chip.remove();
      });
      parseList(textarea.value).forEach(function (domain) {
        var chip = document.createElement("span");
        chip.className = "chip";
        chip.appendChild(document.createTextNode(domain + " "));
        var button = document.createElement("button");
        button.type = "button";
        button.setAttribute("aria-label", "Remove " + domain);
        button.textContent = "×";
        button.addEventListener("click", function () {
          textarea.value = parseList(textarea.value)
            .filter(function (item) {
              return item !== domain;
            })
            .join(", ");
          render();
        });
        chip.appendChild(button);
        wrap.insertBefore(chip, input);
      });
    }

    function commit() {
      var next = input.value.trim().replace(/,$/, "");
      if (!next) return;
      var items = parseList(textarea.value);
      if (items.indexOf(next) === -1) {
        items.push(next);
      }
      textarea.value = items.join(", ");
      input.value = "";
      render();
    }

    input.addEventListener("keydown", function (event) {
      if (event.key === "Enter" || event.key === ",") {
        event.preventDefault();
        commit();
      }
    });
    input.addEventListener("blur", commit);
    render();
  }

  function overlay(show) {
    var el = document.getElementById("pipeline-overlay");
    if (!el) return;
    el.hidden = !show;
    document.body.style.overflow = show ? "hidden" : "";
  }

  async function readJson(response) {
    try {
      return await response.json();
    } catch (err) {
      return null;
    }
  }

  async function runPipeline(profileUuid, button) {
    overlay(true);
    if (button) button.disabled = true;
    try {
      var response = await fetch("/api/v1/profiles/" + profileUuid + "/run", {
        method: "POST",
        headers: { Accept: "application/json" },
      });
      var body = await readJson(response);
      if (!response.ok) {
        overlay(false);
        toast(errorMessage(body, "Pipeline failed"), "error");
        if (button) button.disabled = false;
        return;
      }
      window.location.reload();
    } catch (err) {
      overlay(false);
      toast("Could not reach the API.", "error");
      if (button) button.disabled = false;
    }
  }

  async function recheckQuery(queryUuid, button) {
    var original = button.textContent;
    button.disabled = true;
    button.textContent = "Checking…";
    try {
      var response = await fetch("/api/v1/queries/" + queryUuid + "/recheck", {
        method: "POST",
        headers: { Accept: "application/json" },
      });
      var body = await readJson(response);
      if (!response.ok) {
        toast(errorMessage(body, "Recheck failed"), "error");
        button.disabled = false;
        button.textContent = original;
        return;
      }
      window.location.reload();
    } catch (err) {
      toast("Could not reach the API.", "error");
      button.disabled = false;
      button.textContent = original;
    }
  }

  document.querySelectorAll("[data-chip-field]").forEach(enhanceChipField);
  document.querySelectorAll("[data-run-pipeline]").forEach(function (button) {
    button.addEventListener("click", function () {
      runPipeline(button.getAttribute("data-run-pipeline"), button);
    });
  });
  document.querySelectorAll("[data-recheck]").forEach(function (button) {
    button.addEventListener("click", function () {
      recheckQuery(button.getAttribute("data-recheck"), button);
    });
  });
  dismissToasts();
})();
