using System;
using UnityEngine;

namespace GameFactory.Core
{
    /// <summary>
    /// Single "tap anywhere" detector shared by every genre. Reacts to Android
    /// touch input and to the mouse so gameplay can be tested in the Editor.
    /// One MonoBehaviour, one Update() call, regardless of how many systems
    /// need to react to a tap.
    /// </summary>
    public class TapInput : MonoBehaviour
    {
        public static event Action Tapped;

        private void Update()
        {
            if (Input.GetMouseButtonDown(0))
            {
                Tapped?.Invoke();
                return;
            }

            if (Input.touchCount > 0 && Input.GetTouch(0).phase == TouchPhase.Began)
            {
                Tapped?.Invoke();
            }
        }
    }
}
