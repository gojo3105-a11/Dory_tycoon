using System.Collections.Generic;
using UnityEngine;

namespace GameFactory.Core
{
    /// <summary>
    /// Minimal prefab object pool. Spawners across every genre use this
    /// instead of Instantiate/Destroy to keep GC allocations and CPU spikes
    /// low on low-end Android devices.
    /// </summary>
    public class GameObjectPool : MonoBehaviour
    {
        private GameObject prefab;
        private readonly Queue<GameObject> available = new Queue<GameObject>();

        public void Initialize(GameObject prefabToPool, int prewarmCount = 0)
        {
            prefab = prefabToPool;
            for (int i = 0; i < prewarmCount; i++)
            {
                GameObject instance = Instantiate(prefab, transform);
                instance.SetActive(false);
                available.Enqueue(instance);
            }
        }

        public GameObject Get(Vector3 position, Quaternion rotation)
        {
            GameObject instance = available.Count > 0 ? available.Dequeue() : Instantiate(prefab, transform);
            instance.transform.SetPositionAndRotation(position, rotation);
            instance.SetActive(true);
            return instance;
        }

        public void Release(GameObject instance)
        {
            instance.SetActive(false);
            available.Enqueue(instance);
        }
    }
}
