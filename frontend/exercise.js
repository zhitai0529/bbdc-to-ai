export function mountExercise(section, { api, renderMarkdown, onBusyChange }) {
  const level = section.querySelector("#exerciseLevel");
  const kind = section.querySelector("#exerciseType");
  const description = section.querySelector("#exerciseDescription");
  const generate = section.querySelector("#generateExercise");
  const feedback = section.querySelector("#exerciseStatus");
  const preview = section.querySelector("#exercisePreview");
  const filename = section.querySelector("#exerciseFilename");
  const markdown = section.querySelector("#exerciseMarkdown");
  const copy = section.querySelector("#copyExercise");
  let types = [];
  let data;
  let result;
  let blocked = false;
  let pending = false;
  let customLevel = false;
  let revision = 0;

  function controls() {
    const disabled = blocked || pending || !data;
    level.disabled = disabled;
    kind.disabled = disabled || !types.length;
    generate.disabled = disabled || !kind.value;
    copy.disabled = pending || !result;
  }

  function clearPreview() {
    revision++;
    result = undefined;
    feedback.textContent = "";
    preview.hidden = true;
    filename.textContent = "";
    markdown.replaceChildren();
    controls();
  }

  function describeType() {
    description.textContent =
      types.find((type) => type.id === kind.value)?.description ??
      "暂无可用练习题型。";
  }

  level.onchange = () => {
    customLevel = true;
    clearPreview();
  };
  kind.onchange = () => {
    clearPreview();
    describeType();
  };
  generate.onclick = async () => {
    if (generate.disabled) return;
    clearPreview();
    const request = revision;
    pending = true;
    onBusyChange();
    feedback.textContent = "正在生成练习提示词…";
    try {
      const exported = await api().export_exercise(data.day, level.value, kind.value);
      if (request !== revision) return;
      markdown.innerHTML = renderMarkdown(exported.markdown);
      result = exported;
      filename.textContent = exported.filename;
      preview.hidden = false;
      feedback.textContent = `已保存练习提示词，使用 ${exported.word_count} 个待复习词。`;
    } catch (error) {
      if (request === revision)
        feedback.textContent = error?.message || String(error);
    } finally {
      pending = false;
      onBusyChange();
    }
  };
  copy.onclick = async () => {
    if (!result) return;
    const copied = result;
    try {
      await api().copy(copied.markdown);
      if (result === copied) feedback.textContent = "已复制练习提示词，可以粘贴给 AI。";
    } catch (error) {
      if (result === copied) feedback.textContent = error?.message || String(error);
    }
  };

  return {
    get pending() {
      return pending;
    },
    setBlocked(value) {
      blocked = value;
      controls();
    },
    update(snapshot) {
      const previousLevel = level.value;
      const previousKind = kind.value;
      if (!customLevel) level.value = snapshot.review_level ?? "postgrad";
      types = snapshot.exercise_types ?? [];
      kind.replaceChildren(...types.map((type) => new Option(type.label, type.id)));
      if (types.some((type) => type.id === previousKind)) kind.value = previousKind;
      const changed =
        snapshot.day !== data?.day || snapshot.folder !== data?.folder ||
        level.value !== previousLevel || kind.value !== previousKind;
      data = snapshot;
      if (changed) clearPreview();
      describeType();
      controls();
    },
  };
}
