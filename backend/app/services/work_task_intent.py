# ruff: noqa: RUF001
"""Conservative, zero-I/O commands; uncertain messages never rewrite a goal."""

import re


def intent(text):
    text = text.strip()
    if re.fullmatch(r"(?:请|先|帮我)?(?:暂停|停止一下)(?:当前|这个|该)?任务[。！!]?", text):
        return "pause"
    if re.fullmatch(r"(?:请|帮我)?取消(?:当前|这个|该)?任务[。！!]?", text):
        return "cancel"
    if re.fullmatch(r"(?:当前|这个|该)?任务(?:已完成|完成了|结束了)[。！!]?", text):
        return "complete"
    if re.match(
        r"^(?:请|帮我)?(?:修改(?:当前|这个)?任务(?:要求|目标)?|调整(?:当前|这个)?任务|把(?:当前|这个)?任务改成|任务要求改为|改成|改为)",
        text,
    ):
        return "revise"
    if re.fullmatch(
        r"(?:请|帮我)?(?:继续|接着做|继续执行|继续开发|继续任务|继续之前的任务|恢复任务)[。！!]?",
        text,
    ):
        return "continue"
    if re.match(r"^(?:请|帮我)?(?:继续(?:当前|之前|这个|上次)的?任务|回到之前的任务)", text):
        return "continue"
    explicit = re.match(r"^(?:请|帮我)?(?:创建|新建|开始)(?:一个)?(?:长期|工作|新)?任务[：:]", text)
    deliverable = re.search(
        r"报告|文档|PPT|Word|Excel|应用|网站|程序|功能|项目|report|application", text, re.I
    )
    actions = re.findall(
        r"分析|比较|对比|检索|整理|验证|测试|生成|导出|设计|实现|开发|修复|analy[sz]e|compare|build|test|export",
        text,
        re.I,
    )
    if explicit or (len(text) >= 12 and deliverable and len(set(actions)) >= 2):
        return "new"
    return None
