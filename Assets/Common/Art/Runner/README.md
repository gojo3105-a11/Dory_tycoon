# Assets/Common/Art/Runner

Runner 장르가 쓰는 **실제 아트**를 놓는 곳이다. 여기 파일이 있으면
`PrefabGenerator`가 절차 생성 단색 placeholder 대신 이걸 쓴다.

## 생성기가 찾는 정확한 파일명

| 파일 | 쓰이는 곳 | 없으면 |
|---|---|---|
| `ground.png` | GroundTile (Tiled 드로우) | 테마 해시 기반 단색 |
| `obstacle.png` | Obstacle | 빨간 사각형 |
| `coin.png` | Coin | 노란 사각형 |
| `gravity_zone.png` | GravityZone (Tiled 드로우) | 보라 반투명 사각형 |

이름이 정확히 맞아야 한다. **하나만 넣어도 된다** — 넣은 것만 교체되고 나머지는
placeholder로 남는다. 폴더가 비어 있으면 동작은 지금과 완전히 동일하다.

## 넣으면 자동으로 되는 것

`Assets/GameFactory/Editor/SharedArtImporter.cs`(AssetPostprocessor)가
`Assets/Common/Art/` 아래 텍스처의 임포트 설정을 자동으로 잡는다:

- Texture Type = Sprite (Single)
- **Mesh Type = Full Rect** — 중요. `SpriteRenderer.drawMode = Tiled`(ground,
  gravity_zone이 사용)은 기본값인 Tight 메시로 임포트된 스프라이트를 타일링하지
  **못하고 조용히 실패한다**
- Pixels Per Unit = 64, Point 필터, mipmap 끔, alpha is transparency

이 설정은 **최초 임포트 때만** 찍힌다(`importSettingsMissing` 검사). 나중에
Inspector에서 개별 조정한 값을 재임포트 때마다 되돌리지 않기 위해서다.

콜라이더 크기는 스프라이트 실제 크기에서 계산한다(`SpriteWorldSize`). 그래서
아트 해상도가 64px가 아니어도 보이는 것과 판정이 어긋나지 않는다.

## 라이선스 (§8 - 반드시 지킬 것)

**여기 넣는 모든 파일은 `AI_GAME_COMPANY/config/LICENSE_REGISTRY.json`에
등록되어야 하고, status가 `APPROVED`가 아니면 출시 APK에 들어갈 수 없다.**

출처가 확실하지 않은 이미지를 그냥 복사해 넣지 말 것. 마스터 프롬프트 §38이
`License UNKNOWN Asset 출시`를 명시적으로 금지한다.

권장 절차:

1. 브라우저로 아트 팩 zip을 받아서 `AI_GAME_COMPANY/asset_staging/_incoming/`에 넣는다
2. `.\AI_GAME_COMPANY\tools\fetch-cc0-assets.ps1 -Commit` 실행 —
   zip 안에 동봉된 라이선스 파일 + 아카이브 SHA-256 + 이미지 목록을 증거로 커밋한다
   (`Assets/`는 건드리지 않는다)
3. 라이선스 텍스트 검토 후 레지스트리를 `APPROVED`로 올리고, 인벤토리에서 고른 파일을
   위 표의 이름으로 여기에 복사한다
