# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Dory Tycoon은 Android 모바일용 2D 아이소메트릭 힐링 음식점 타이쿤 게임이다.

플레이어는 고슴도치 도리가 운영하는 작은 숲속 음식점을 성장시킨다.

게임은 작은 식당에서 시작하며, 이후 텃밭, 베이커리, 야외 테이블, 정원, 푸드마켓이 있는 숲속 음식 마을로 확장된다.

## Development Environment

- Engine: Godot 4.x
- Language: GDScript
- Platform: Android
- Orientation: Portrait 9:16
- Input: Touch first
- Development device: Android smartphone
- Repository: Dory_tycoon

## Core Game Concept

핵심 플레이 흐름은 다음과 같다.

1. 손님이 등장한다.
2. 빈 테이블로 이동한다.
3. 주문을 생성한다.
4. 조리대에서 음식이 자동으로 조리된다.
5. 도리가 완성된 음식을 손님에게 전달한다.
6. 손님이 식사한다.
7. 손님이 자동으로 결제한다.
8. 골드가 증가한다.
9. 손님이 퇴장한다.
10. 플레이어는 골드로 식당을 업그레이드한다.

## MVP 1 Scope

첫 번째 MVP에는 아래 기능만 구현한다.

- 작은 식당 한 화면
- 테이블 2개
- 조리대 1개
- 도리 1명
- 손님 1종
- 손님 자동 등장
- 빈 테이블 선택
- 주문 생성
- 자동 조리
- 도리의 서빙
- 식사
- 자동 결제
- 골드 증가
- 손님 퇴장
- 저장 및 불러오기
- 테이블 추가 업그레이드

MVP 1에서는 아래 기능을 구현하지 않는다.

- 농장
- 재료 재고
- 자유로운 건물 배치
- 직원 고용
- 베이커리
- 차량
- 날씨
- 계절
- 광고
- 인앱결제
- 온라인 기능
- 복잡한 길 찾기

## Visual Direction

아트 스타일은 밝고 선명한 2D 카툰 아이소메트릭이다.

기준:

- 따뜻한 갈색, 초록색, 크림색 중심
- 둥글고 단순한 오브젝트
- 모바일 화면에서 쉽게 구분되는 실루엣
- 좌측 상단 광원
- 우측 하단 그림자
- 투명 PNG 사용
- 픽셀아트, 수채화, 3D 클레이 스타일을 혼합하지 않는다
- 실제 이미지 적용 전에는 단순한 도형과 임시 그래픽을 사용한다

## Character Roles

### Dory

도리는 음식 서빙만 담당한다.

도리 상태:

- IDLE
- MOVE_TO_KITCHEN
- PICK_UP_FOOD
- MOVE_TO_CUSTOMER
- SERVE
- RETURN_TO_IDLE

### Customer

손님 상태:

- SPAWN
- MOVE_TO_TABLE
- ORDER
- WAIT
- EAT
- PAY
- LEAVE

손님이 사용할 수 있는 테이블이 없으면 일정 시간 기다리지 않고 퇴장한다.

## Initial Food Data

### Carrot Soup

- Cook time: 4 seconds
- Price: 12 gold

### Sandwich

- Cook time: 5 seconds
- Price: 18 gold

### Apple Juice

- Cook time: 3 seconds
- Price: 10 gold

MVP 1에서는 실제 재료를 소비하지 않는다.

## Initial Upgrade Data

### Add Table

- Cost: 100 gold
- Effect: Adds one customer seat

### Faster Cooking

- Cost: 150 gold
- Effect: Reduces cooking time by 10 percent

### Menu Upgrade

- Cost: 200 gold
- Effect: Increases selling price by 10 percent

### Restaurant Expansion

- Cost: 500 gold
- Effect: Changes restaurant appearance and adds one table

초기 버전에서는 복잡한 수식을 사용하지 않고 고정 가격표를 사용한다.

## Mobile UI

### Top UI

- Gold
- Level
- Settings

### Main Area

- Restaurant
- Tables
- Cooking station
- Dory
- Customers

### Bottom UI

- Upgrade button
- Menu button
- Quest button

모든 주요 터치 버튼은 충분히 크게 만든다.

작은 캐릭터나 오브젝트를 터치해야 할 경우 실제 이미지보다 큰 터치 영역을 사용한다.

## Project Structure

```text
res://
├─ scenes/
│  ├─ main/
│  ├─ restaurant/
│  ├─ characters/
│  ├─ objects/
│  └─ ui/
├─ scripts/
│  ├─ restaurant/
│  ├─ characters/
│  ├─ objects/
│  └─ ui/
├─ autoload/
│  ├─ game_manager.gd
│  └─ save_manager.gd
├─ data/
│  └─ foods.json
└─ assets/
   ├─ characters/
   ├─ buildings/
   ├─ furniture/
   ├─ food/
   └─ ui/
```

## Coding Rules

- Godot 4.x 문법만 사용한다.
- GDScript를 사용한다.
- 가능한 경우 타입 힌트를 사용한다.
- 한 스크립트에 너무 많은 책임을 넣지 않는다.
- UI, 게임 상태, 캐릭터 상태를 분리한다.
- 기존 파일을 수정하기 전에 반드시 내용을 확인한다.
- `.godot/` 폴더는 수정하지 않는다.
- 에셋 경로를 임의로 변경하지 않는다.
- 한 번에 하나의 기능만 구현한다.
- 구현 후 변경 파일 목록을 보고한다.
- 오류가 발생하면 원인을 먼저 설명한다.
- 기존 정상 기능을 임의로 제거하지 않는다.
- 사용자의 허락 없이 커밋하거나 푸시하지 않는다.

## Validation

가능하다면 수정 후 아래 검사를 실행한다.

```text
godot --headless --path . --editor --quit
```

Android 환경에서 명령 실행이 불가능하다면:

- GDScript 문법을 수동 검토한다.
- 씬 리소스 경로를 확인한다.
- Node 경로와 signal 연결을 확인한다.
- 실행하지 못한 검사는 명확하게 보고한다.

## Development Method

항상 다음 순서를 따른다.

1. 현재 파일 구조 분석
2. 구현 계획 제시
3. 사용자 승인 대기
4. 최소 범위 구현
5. 오류 검사
6. 변경 내용 요약
7. 다음 작업 제안

한 번에 전체 게임을 구현하지 않는다.
