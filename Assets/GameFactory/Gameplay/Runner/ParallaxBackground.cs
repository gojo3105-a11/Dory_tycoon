using UnityEngine;

namespace GameFactory.Gameplay.Runner
{
    /// <summary>Scrolls seamless background strips at independent parallax rates.</summary>
    public class ParallaxBackground : MonoBehaviour
    {
        [SerializeField] private Transform[] layers;
        [SerializeField] private float[] layerWidths;
        [SerializeField] private float[] startingXPositions;
        [SerializeField] private float scrollSpeed;
        [SerializeField] private float[] speedFactors;

        /// <summary>Wires layer strips and caches their sprite widths. Called at edit time.</summary>
        public void SetLayers(Transform[] layerTransforms)
        {
            layers = layerTransforms;

            int layerCount = layers == null ? 0 : layers.Length;
            layerWidths = new float[layerCount];
            startingXPositions = new float[layerCount];

            for (int i = 0; i < layerCount; i++)
            {
                Transform layer = layers[i];
                if (layer == null) continue;

                startingXPositions[i] = layer.localPosition.x;

                // A strip contains adjacent copies; one source sprite defines its repeat interval.
                SpriteRenderer widthSource = layer.GetComponentInChildren<SpriteRenderer>(true);
                if (widthSource != null && widthSource.sprite != null)
                {
                    float parentScale = layer.parent == null
                        ? 1f
                        : Mathf.Abs(layer.parent.lossyScale.x);

                    if (parentScale > 0f)
                    {
                        layerWidths[i] = widthSource.sprite.bounds.size.x
                            * Mathf.Abs(widthSource.transform.lossyScale.x)
                            / parentScale;
                    }
                }
            }
        }

        /// <summary>Sets the runtime scroll rate and one speed factor per layer.</summary>
        public void Configure(float horizontalSpeed, float[] perLayerSpeedFactors)
        {
            scrollSpeed = horizontalSpeed;
            speedFactors = perLayerSpeedFactors;
        }

        private void Update()
        {
            if (layers == null || layerWidths == null || startingXPositions == null
                || speedFactors == null)
            {
                return;
            }

            int layerCount = Mathf.Min(
                layers.Length,
                Mathf.Min(layerWidths.Length, Mathf.Min(startingXPositions.Length, speedFactors.Length)));

            for (int i = 0; i < layerCount; i++)
            {
                Transform layer = layers[i];
                float width = layerWidths[i];
                if (layer == null || width <= 0f) continue;

                float movement = scrollSpeed * speedFactors[i] * Time.deltaTime;
                Vector3 position = layer.localPosition;
                position.x -= movement;

                if (movement > 0f)
                {
                    while (position.x <= startingXPositions[i] - width)
                    {
                        position.x += width;
                    }
                }
                else if (movement < 0f)
                {
                    while (position.x >= startingXPositions[i] + width)
                    {
                        position.x -= width;
                    }
                }

                layer.localPosition = position;
            }
        }
    }
}
