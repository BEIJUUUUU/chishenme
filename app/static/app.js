/* 吃什么？前端交互：极简原生 JS，不依赖任何 CDN，离线 NAS 可用 */

(function () {
  "use strict";

  /* ---------- 长任务遮罩 ---------- */
  function ensureOverlay() {
    let overlay = document.getElementById("busy-overlay");
    if (!overlay) {
      overlay = document.createElement("div");
      overlay.id = "busy-overlay";
      overlay.innerHTML = '<div class="spinner"></div><div id="busy-text">处理中…</div>';
      document.body.appendChild(overlay);
    }
    return overlay;
  }

  function showBusy(text) {
    const overlay = ensureOverlay();
    document.getElementById("busy-text").textContent = text || "处理中…";
    overlay.classList.add("on");
  }

  document.addEventListener("submit", function (event) {
    const form = event.target;
    if (!(form instanceof HTMLFormElement)) return;
    if (form.dataset.noBusy === "1") return;
    const text = form.dataset.busy || "处理中…";
    showBusy(text);
    // 防止连点重复提交
    setTimeout(function () {
      form.querySelectorAll("button[type=submit]").forEach(function (btn) {
        btn.disabled = true;
      });
    }, 0);
  });

  window.addEventListener("pageshow", function () {
    const overlay = document.getElementById("busy-overlay");
    if (overlay) overlay.classList.remove("on");
  });

  /* ---------- 设置页 Tab ---------- */
  document.addEventListener("click", function (event) {
    const tab = event.target.closest(".tab");
    if (!tab) return;
    event.preventDefault();
    document.querySelectorAll(".tab").forEach(function (t) {
      t.classList.toggle("active", t === tab);
    });
    document.querySelectorAll(".tab-panel").forEach(function (panel) {
      panel.classList.toggle("active", panel.id === tab.dataset.tab);
    });
    window.scrollTo({ top: 0, behavior: "smooth" });
  });

  /* ---------- 条件显示字段（depends_on） ---------- */
  function refreshDepends() {
    document.querySelectorAll("[data-depends]").forEach(function (node) {
      const raw = node.getAttribute("data-depends");
      if (!raw || raw === "\"\"" || raw === "null") {
        node.style.display = "";
        return;
      }
      let rule;
      try {
        rule = JSON.parse(raw);
      } catch (err) {
        node.style.display = "";
        return;
      }
      let visible = true;
      Object.keys(rule).forEach(function (key) {
        const control = document.getElementById(key);
        if (!control) return;
        if (String(control.value) !== String(rule[key])) visible = false;
      });
      node.style.display = visible ? "" : "none";
    });
  }

  document.addEventListener("change", function (event) {
    if (event.target && event.target.id === "llm_mode") refreshDepends();
  });

  /* ---------- 复制到剪贴板 ---------- */
  document.addEventListener("click", function (event) {
    const btn = event.target.closest("[data-copy-target]");
    if (!btn) return;
    const target = document.getElementById(btn.dataset.copyTarget);
    if (!target) return;
    const text = target.textContent;
    const done = function () {
      const original = btn.textContent;
      btn.textContent = "已复制 ✓";
      setTimeout(function () {
        btn.textContent = original;
      }, 1600);
    };
    if (navigator.clipboard && window.isSecureContext) {
      navigator.clipboard.writeText(text).then(done).catch(function () {
        fallbackCopy(text, done);
      });
    } else {
      fallbackCopy(text, done);
    }
  });

  function fallbackCopy(text, done) {
    const area = document.createElement("textarea");
    area.value = text;
    area.style.position = "fixed";
    area.style.opacity = "0";
    document.body.appendChild(area);
    area.select();
    try {
      document.execCommand("copy");
      done();
    } catch (err) {
      alert("复制失败，请手动选择文本复制");
    }
    document.body.removeChild(area);
  }

  /* ---------- 异步测试按钮 ---------- */
  function showResult(el, ok, message) {
    if (!el) return;
    el.style.display = "block";
    el.className = "flash " + (ok ? "flash-ok" : "flash-error");
    el.textContent = message;
  }

  async function postJSON(url) {
    const resp = await fetch(url, { method: "POST", headers: { "Accept": "application/json" } });
    let data = {};
    try {
      data = await resp.json();
    } catch (err) {
      data = { ok: false, message: "返回内容无法解析（HTTP " + resp.status + "）" };
    }
    if (resp.status === 401) {
      window.location.href = "/login";
      return { ok: false, message: "登录状态已过期" };
    }
    return data;
  }

  const testLlm = document.getElementById("test-llm-btn");
  if (testLlm) {
    testLlm.addEventListener("click", async function () {
      const box = document.getElementById("llm-result");
      testLlm.disabled = true;
      showResult(box, true, "测试中，本地大模型首次加载可能要等一会儿…");
      box.className = "flash flash-warn";
      const data = await postJSON("/api/test/llm");
      showResult(box, !!data.ok, data.message || String(data));
      testLlm.disabled = false;
    });
  }

  document.querySelectorAll(".test-push-btn").forEach(function (btn) {
    btn.addEventListener("click", async function () {
      const box = document.getElementById("push-result");
      btn.disabled = true;
      showResult(box, true, "正在发送测试消息…");
      box.className = "flash flash-warn";
      const data = await postJSON("/api/test/push/" + encodeURIComponent(btn.dataset.channel));
      showResult(box, !!data.ok, (data.channel || "") + "：" + (data.message || ""));
      btn.disabled = false;
    });
  });

  /* ---------- 初始化 ---------- */
  refreshDepends();
})();
