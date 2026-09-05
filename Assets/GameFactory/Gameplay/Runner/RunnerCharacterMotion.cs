using UnityEngine;

namespace GameFactory.Gameplay.Runner
{
    /// <summary>
    /// Makes a single static sprite read as a character that is running,
    /// jumping and landing - without a single extra frame of art.
    ///
    /// WHY THIS EXISTS. 도리 is one cut-out PNG. There is no animator, no
    /// sprite sheet, no rig, so the character otherwise slides along the ground
    /// as a decal. Squash and stretch, a run bob and a lean carry most of what
    /// a run cycle communicates - weight, rhythm, and the moment of impact -
    /// and they cost nothing per frame. Real frames, when they exist, layer on
    /// top of this rather than replacing it: animators keep using squash and
    /// stretch precisely because frames alone do not sell weight.
    ///
    /// VISUAL ONLY. This lives on a child transform and scales and rotates that
    /// child. Putting it on the player root would scale the BoxCollider2D with
    /// it, so the hitbox would breathe in and out while running - which is the
    /// same class of bug as the collider/visual offset that made coin pickups
    /// feel wrong.
    /// </summary>
    [DisallowMultipleComponent]
    public class RunnerCharacterMotion : MonoBehaviour
    {
        [Header("Run")]
        [Tooltip("Bounces per second while grounded.")]
        [SerializeField] private float bobFrequency = 4.5f;
        [Tooltip("Vertical travel of the bob, in world units.")]
        [SerializeField] private float bobHeight = 0.045f;
        [Tooltip("How much the body squashes at the bottom of each bob, 0-1.")]
        [SerializeField] private float bobSquash = 0.055f;
        [Tooltip("Forward lean while running, in degrees.")]
        [SerializeField] private float runLean = 5f;

        [Header("Limbs")]
        [Tooltip("Maximum limb rotation during the grounded run cycle, in degrees.")]
        [SerializeField] private float limbSwing = 13f;
        [Tooltip("Arm angle held while airborne, in degrees.")]
        [SerializeField] private float jumpArmAngle = 18f;
        [Tooltip("Leg angle held while airborne, in degrees.")]
        [SerializeField] private float jumpLegAngle = 11f;
        [SerializeField] private Color limbColor = new Color(0.95f, 0.87f, 0.75f, 1f);

        [Header("Air")]
        [Tooltip("Vertical speed that produces the full stretch or squash.")]
        [SerializeField] private float velocityForFullStretch = 12f;
        [Tooltip("Peak stretch while rising, 0-1.")]
        [SerializeField] private float airStretch = 0.16f;
        [Tooltip("Backward tilt at the top of a jump, in degrees.")]
        [SerializeField] private float airTilt = 9f;

        [Header("Landing")]
        [Tooltip("Squash applied the instant the feet touch down, 0-1.")]
        [SerializeField] private float landSquash = 0.22f;
        [Tooltip("Seconds for the landing squash to spring back.")]
        [SerializeField] private float landRecovery = 0.18f;

        [Header("Response")]
        [Tooltip("Seconds for scale to chase its target. Small is snappy.")]
        [SerializeField] private float scaleSmoothing = 0.045f;
        [SerializeField] private float rotationSmoothing = 0.08f;

        private RunnerPlayerController controller;
        private Vector3 baseScale;
        private Vector3 baseLocalPosition;
        // Half the sprite's height in world units. The pivot is Center, so a
        // squash lifts the feet by exactly this much times the scale lost.
        private float spriteHalfHeight;

        private Transform leftArm;
        private Transform rightArm;
        private Transform leftLeg;
        private Transform rightLeg;
        private static Sprite limbSprite;

        private float bobPhase;
        private float landTimer;
        private bool wasGrounded = true;

        // Smoothed state, so a frame spike does not pop the character.
        private Vector2 scaleVelocity;
        private Vector2 currentScale = Vector2.one;
        private float currentAngle;
        private float angleVelocity;

        /// <summary>Structural wiring, set at edit time by PrefabGenerator.</summary>
        public void SetController(RunnerPlayerController owner)
        {
            controller = owner;
        }

        private void Awake()
        {
            baseScale = transform.localScale;
            baseLocalPosition = transform.localPosition;
            if (controller == null) controller = GetComponentInParent<RunnerPlayerController>();

            SpriteRenderer renderer = GetComponent<SpriteRenderer>();
            spriteHalfHeight = renderer != null && renderer.sprite != null
                ? renderer.sprite.bounds.extents.y * baseScale.y
                : 0.5f;

            CreateLimbs(renderer);
        }

        private void OnDisable()
        {
            // Leave the visual exactly as generated, so a disabled component
            // never bakes a squashed pose into the prefab.
            transform.localScale = baseScale;
            transform.localPosition = baseLocalPosition;
            transform.localRotation = Quaternion.identity;
            SetLimbAngles(0f, 0f, 0f, 0f);
        }

        private void LateUpdate()
        {
            if (controller == null) return;

            float dt = Time.deltaTime;
            if (dt <= 0f) return;

            bool grounded = controller.IsGrounded;
            bool dead = controller.IsDead;

            if (grounded && !wasGrounded) landTimer = landRecovery;
            wasGrounded = grounded;
            if (landTimer > 0f) landTimer = Mathf.Max(0f, landTimer - dt);

            Vector2 targetScale = Vector2.one;
            float targetAngle = 0f;
            float bobOffset = 0f;
            float leftArmAngle = 0f;
            float rightArmAngle = 0f;
            float leftLegAngle = 0f;
            float rightLegAngle = 0f;

            if (dead)
            {
                // Flattened and tipped over: the run reads as stopped rather
                // than paused.
                targetScale = new Vector2(1f + landSquash, 1f - landSquash);
                targetAngle = -25f;
            }
            else if (grounded)
            {
                bobPhase += dt * bobFrequency * Mathf.PI * 2f;
                float bob = Mathf.Sin(bobPhase);

                bobOffset = Mathf.Max(0f, bob) * bobHeight;
                // Squash at the bottom of the arc, where the weight lands.
                float squash = Mathf.Max(0f, -bob) * bobSquash;
                targetScale = new Vector2(1f + squash, 1f - squash);
                targetAngle = -runLean;

                float swing = bob * limbSwing;
                // Diagonal pairs share a phase so the tiny silhouette still
                // reads as a coordinated run rather than four flailing parts.
                leftArmAngle = swing;
                rightLegAngle = swing;
                rightArmAngle = -swing;
                leftLegAngle = -swing;
            }
            else
            {
                float vertical = Mathf.Clamp(
                    controller.VerticalVelocity / velocityForFullStretch, -1f, 1f);
                // Rising stretches, falling squashes - the classic read.
                float stretch = vertical * airStretch;
                targetScale = new Vector2(1f - stretch, 1f + stretch);
                targetAngle = -runLean + vertical * airTilt;
                bobPhase = 0f;

                leftArmAngle = -jumpArmAngle;
                rightArmAngle = jumpArmAngle;
                leftLegAngle = -jumpLegAngle;
                rightLegAngle = jumpLegAngle;
            }

            if (landTimer > 0f)
            {
                float t = landTimer / Mathf.Max(0.0001f, landRecovery);
                float impact = landSquash * t * t;
                targetScale = new Vector2(targetScale.x + impact, targetScale.y - impact);
            }

            currentScale = new Vector2(
                Mathf.SmoothDamp(currentScale.x, targetScale.x, ref scaleVelocity.x, scaleSmoothing),
                Mathf.SmoothDamp(currentScale.y, targetScale.y, ref scaleVelocity.y, scaleSmoothing));
            currentAngle = Mathf.SmoothDampAngle(
                currentAngle, targetAngle, ref angleVelocity, rotationSmoothing);

            transform.localScale = new Vector3(
                baseScale.x * currentScale.x, baseScale.y * currentScale.y, baseScale.z);
            transform.localRotation = Quaternion.Euler(0f, 0f, currentAngle);

            // Anchor the feet. The pivot is the sprite's centre, so squashing
            // to scale s lifts the feet by spriteHalfHeight * (1 - s); without
            // this the character bounces off the ground every time it lands.
            float footCompensation = (1f - currentScale.y) * spriteHalfHeight;
            transform.localPosition = baseLocalPosition
                + new Vector3(0f, bobOffset - footCompensation, 0f);

            SetLimbAngles(leftArmAngle, rightArmAngle, leftLegAngle, rightLegAngle);
        }

        private void CreateLimbs(SpriteRenderer bodyRenderer)
        {
            if (bodyRenderer == null || bodyRenderer.sprite == null) return;

            if (limbSprite == null)
            {
                Texture2D texture = new Texture2D(1, 1, TextureFormat.RGBA32, false);
                texture.name = "Runner Limb Texture";
                texture.hideFlags = HideFlags.HideAndDontSave;
                texture.filterMode = FilterMode.Point;
                texture.SetPixel(0, 0, Color.white);
                texture.Apply(false, true);

                limbSprite = Sprite.Create(
                    texture, new Rect(0f, 0f, 1f, 1f), new Vector2(0.5f, 1f), 1f);
                limbSprite.name = "Runner Limb Sprite";
                limbSprite.hideFlags = HideFlags.HideAndDontSave;
            }

            Vector2 bodySize = bodyRenderer.sprite.bounds.size;
            float armWidth = bodySize.x * 0.075f;
            float armLength = bodySize.y * 0.25f;
            float legWidth = bodySize.x * 0.09f;
            float legLength = bodySize.y * 0.23f;

            leftArm = CreateLimb(
                "Left Arm", new Vector2(-bodySize.x * 0.31f, bodySize.y * 0.19f),
                new Vector2(armWidth, armLength), bodyRenderer);
            rightArm = CreateLimb(
                "Right Arm", new Vector2(bodySize.x * 0.31f, bodySize.y * 0.19f),
                new Vector2(armWidth, armLength), bodyRenderer);
            leftLeg = CreateLimb(
                "Left Leg", new Vector2(-bodySize.x * 0.14f, -bodySize.y * 0.26f),
                new Vector2(legWidth, legLength), bodyRenderer);
            rightLeg = CreateLimb(
                "Right Leg", new Vector2(bodySize.x * 0.14f, -bodySize.y * 0.26f),
                new Vector2(legWidth, legLength), bodyRenderer);
        }

        private Transform CreateLimb(
            string limbName, Vector2 jointPosition, Vector2 size, SpriteRenderer bodyRenderer)
        {
            GameObject limb = new GameObject(limbName);
            Transform limbTransform = limb.transform;
            limbTransform.SetParent(transform, false);
            limbTransform.localPosition = jointPosition;
            limbTransform.localScale = new Vector3(size.x, size.y, 1f);

            SpriteRenderer limbRenderer = limb.AddComponent<SpriteRenderer>();
            limbRenderer.sprite = limbSprite;
            limbRenderer.color = limbColor;
            limbRenderer.sortingLayerID = bodyRenderer.sortingLayerID;
            limbRenderer.sortingOrder = bodyRenderer.sortingOrder - 1;
            return limbTransform;
        }

        private void SetLimbAngles(
            float leftArmDegrees, float rightArmDegrees,
            float leftLegDegrees, float rightLegDegrees)
        {
            if (leftArm == null) return;

            leftArm.localRotation = Quaternion.Euler(0f, 0f, leftArmDegrees);
            rightArm.localRotation = Quaternion.Euler(0f, 0f, rightArmDegrees);
            leftLeg.localRotation = Quaternion.Euler(0f, 0f, leftLegDegrees);
            rightLeg.localRotation = Quaternion.Euler(0f, 0f, rightLegDegrees);
        }
    }
}
