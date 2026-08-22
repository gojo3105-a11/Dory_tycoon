using UnityEngine;

namespace GameFactory.Core
{
    /// <summary>Generic 2D camera follow usable by any genre (Runner follows X only, Puzzle can lock both axes).</summary>
    public class CameraFollow2D : MonoBehaviour
    {
        [SerializeField] private Transform target;
        [SerializeField] private Vector3 offset = new Vector3(2f, 0f, -10f);
        [SerializeField] private bool followX = true;
        [SerializeField] private bool followY;
        [SerializeField] private float smoothTime = 0.15f;

        private Vector3 velocity;

        public void SetTarget(Transform newTarget) => target = newTarget;

        private void LateUpdate()
        {
            if (target == null) return;

            Vector3 desired = transform.position;
            if (followX) desired.x = target.position.x + offset.x;
            if (followY) desired.y = target.position.y + offset.y;
            desired.z = offset.z;

            transform.position = Vector3.SmoothDamp(transform.position, desired, ref velocity, smoothTime);
        }
    }
}
