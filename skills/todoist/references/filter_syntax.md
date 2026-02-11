# Todoist 過濾器快速參考

## 常用過濾器

```bash
# 今日任務
today

# 今日 + 過期
today | overdue

# 高優先級
p1 | p2

# 未來一週
7 days

# 本週
this week

# 無日期
no date
```

## 按專案

```bash
# 特定專案
#工作

# 專案及子專案
##工作

# 排除專案
!#收件匣
```

## 按標籤

```bash
# 特定標籤
@重要

# 多個標籤（任一）
@重要 | @緊急

# 多個標籤（同時）
@重要 & @工作
```

## 按優先級

```bash
# 最高優先級
p1

# 高優先級以上
p1 | p2

# 非低優先級
!p4
```

## 按日期範圍

```bash
# 特定日期
Jan 30

# 日期之前
before: Jan 31

# 日期之後
after: Jan 15

# 日期範圍
after: Jan 15 & before: Feb 1
```

## 組合範例

```bash
# 工作專案中今日到期的高優先任務
#工作 & today & (p1 | p2)

# 過期或今日的重要標籤任務
(overdue | today) & @重要

# 未來 7 天但不含低優先級
7 days & !p4

# 收件匣中無日期的任務
#收件匣 & no date
```

## 人員過濾

```bash
# 指派給我
assigned to: me

# 我指派的
assigned by: me

# 有指派的
assigned

# 未指派的
!assigned
```

## 特殊過濾

```bash
# 循環任務
recurring

# 子任務
subtask

# 共享專案
shared

# 今日建立
created: today

# 有留言
commented
```
