def judge(doc: dict) -> tuple[str, str]:
    steps = doc.get("steps") or []
    fry = next((s for s in steps if s.get("name") == "清炒"), None)
    if fry is None:
        return "未放行", "缺少清炒工序"
    temp = float(fry.get("temp_c", 0))
    minutes = float(fry.get("minutes", 0))
    if not 80 <= temp <= 150:
        return "未放行", "清炒温度不在范围内"
    if not 5 <= minutes <= 30:
        return "未放行", "清炒时长不在范围内"
    return "放行", "清炒工序符合炮制要求"


def clean_foreign_names(names, known_texts) -> list[str]:
    """校验开炒点名：去空白、去重、至少一项、且每项都在异物词条表内。

    通过校验后返回的原文名单会整包存进文书，事后改词条表不影响已存点名。
    """
    cleaned = []
    for raw in names or []:
        text = str(raw).strip()
        if text and text not in cleaned:
            cleaned.append(text)
    if not cleaned:
        raise ValueError("零点名拒写：开炒至少点名一项异物词条")
    unknown = [text for text in cleaned if text not in known_texts]
    if unknown:
        raise ValueError("点名不在异物词条表内：" + "、".join(unknown))
    return cleaned
